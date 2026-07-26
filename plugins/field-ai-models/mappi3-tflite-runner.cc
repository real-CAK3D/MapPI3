// mappi3-tflite-runner: tiny TensorFlow Lite CLI smoke/inference runner for MapPI3.
// Conservative field use: proves runtime/model execution and emits top output indexes;
// labels/class safety are handled by MapPI3 policy, not this runner.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "tensorflow/lite/c/c_api.h"

struct Image { int w=0,h=0,c=3; std::vector<uint8_t> pix; };

static std::string jesc(const std::string& s){ std::string o; for(char ch: s){ if(ch=='"'||ch=='\\') {o+='\\'; o+=ch;} else if((unsigned char)ch<32) o+=' '; else o+=ch;} return o; }
static const char* tname(TfLiteType t){
  switch(t){
    case kTfLiteFloat32: return "float32";
    case kTfLiteInt32: return "int32";
    case kTfLiteUInt8: return "uint8";
    case kTfLiteInt64: return "int64";
    case kTfLiteBool: return "bool";
    case kTfLiteInt16: return "int16";
    case kTfLiteInt8: return "int8";
    default: return "other";
  }
}

static bool read_token(std::istream& in, std::string& tok){
  tok.clear(); char ch;
  while(in.get(ch)){
    if(ch=='#'){ std::string dummy; std::getline(in,dummy); continue; }
    if(!std::isspace((unsigned char)ch)){ tok.push_back(ch); break; }
  }
  while(in.get(ch)){
    if(std::isspace((unsigned char)ch)) break;
    tok.push_back(ch);
  }
  return !tok.empty();
}

static bool load_ppm(const std::string& path, Image& img, std::string& err){
  std::ifstream in(path, std::ios::binary);
  if(!in){ err="open_failed"; return false; }
  std::string tok;
  if(!read_token(in,tok) || tok!="P6"){ err="not_p6_ppm"; return false; }
  if(!read_token(in,tok)){ err="missing_width"; return false; } img.w=std::stoi(tok);
  if(!read_token(in,tok)){ err="missing_height"; return false; } img.h=std::stoi(tok);
  if(!read_token(in,tok)){ err="missing_max"; return false; } int maxv=std::stoi(tok);
  if(maxv!=255){ err="unsupported_maxval"; return false; }
  img.c=3; img.pix.resize((size_t)img.w*img.h*3);
  in.read((char*)img.pix.data(), img.pix.size());
  if((size_t)in.gcount()!=img.pix.size()){ err="short_read"; return false; }
  return true;
}

static void fill_input(TfLiteTensor* t, const Image* img){
  const int nd=TfLiteTensorNumDims(t);
  int h=1,w=1,c=1;
  if(nd==4){ h=TfLiteTensorDim(t,1); w=TfLiteTensorDim(t,2); c=TfLiteTensorDim(t,3); }
  const size_t bytes=TfLiteTensorByteSize(t);
  void* data=TfLiteTensorData(t);
  TfLiteType ty=TfLiteTensorType(t);
  if(!img || img->pix.empty() || nd!=4 || c<1){
    if(ty==kTfLiteUInt8) std::memset(data, 128, bytes);
    else std::memset(data, 0, bytes);
    return;
  }
  for(int yy=0; yy<h; ++yy){
    int sy=std::min(img->h-1, std::max(0, yy*img->h/std::max(1,h)));
    for(int xx=0; xx<w; ++xx){
      int sx=std::min(img->w-1, std::max(0, xx*img->w/std::max(1,w)));
      const uint8_t* sp=&img->pix[((size_t)sy*img->w+sx)*3];
      for(int cc=0; cc<c; ++cc){
        int v=sp[std::min(cc,2)];
        size_t idx=((size_t)yy*w+xx)*c+cc;
        if(ty==kTfLiteUInt8) ((uint8_t*)data)[idx]=(uint8_t)v;
        else if(ty==kTfLiteInt8) ((int8_t*)data)[idx]=(int8_t)(v-128);
        else if(ty==kTfLiteFloat32) ((float*)data)[idx]=(float)v/255.0f;
      }
    }
  }
}

int main(int argc, char** argv){
  std::string model, image;
  for(int i=1;i<argc;i++){
    std::string a=argv[i];
    if((a=="--model"||a=="-m") && i+1<argc) model=argv[++i];
    else if((a=="--ppm"||a=="--image") && i+1<argc) image=argv[++i];
    else if(a=="--info") {}
    else { std::cerr << "usage: mappi3-tflite-runner --model model.tflite [--info] [--ppm image.ppm]\n"; return 2; }
  }
  if(model.empty()){ std::cerr << "missing --model\n"; return 2; }
  TfLiteModel* m=TfLiteModelCreateFromFile(model.c_str());
  if(!m){ std::cout << "{\"ok\":false,\"error\":\"model_load_failed\"}\n"; return 1; }
  TfLiteInterpreterOptions* opt=TfLiteInterpreterOptionsCreate();
  TfLiteInterpreterOptionsSetNumThreads(opt, 1);
  TfLiteInterpreter* interp=TfLiteInterpreterCreate(m,opt);
  if(!interp){ std::cout << "{\"ok\":false,\"error\":\"interpreter_create_failed\"}\n"; return 1; }
  if(TfLiteInterpreterAllocateTensors(interp)!=kTfLiteOk){ std::cout << "{\"ok\":false,\"error\":\"allocate_failed\"}\n"; return 1; }
  int ni=TfLiteInterpreterGetInputTensorCount(interp), no=TfLiteInterpreterGetOutputTensorCount(interp);
  TfLiteTensor* in0=ni?TfLiteInterpreterGetInputTensor(interp,0):nullptr;
  const TfLiteTensor* out0=no?TfLiteInterpreterGetOutputTensor(interp,0):nullptr;
  if(!in0 || !out0){ std::cout << "{\"ok\":false,\"error\":\"missing_tensor\"}\n"; return 1; }
  Image img; std::string imgerr; bool has_img=false;
  if(!image.empty()){ has_img=load_ppm(image,img,imgerr); if(!has_img){ std::cout << "{\"ok\":false,\"error\":\"image_"<<jesc(imgerr)<<"\"}\n"; return 1; } }
  fill_input(in0, has_img?&img:nullptr);
  auto t0=std::chrono::steady_clock::now();
  TfLiteStatus st=TfLiteInterpreterInvoke(interp);
  auto t1=std::chrono::steady_clock::now();
  long ms=std::chrono::duration_cast<std::chrono::milliseconds>(t1-t0).count();
  if(st!=kTfLiteOk){ std::cout << "{\"ok\":false,\"error\":\"invoke_failed\"}\n"; return 1; }
  int outn=1; for(int d=0; d<TfLiteTensorNumDims(out0); ++d) outn*=std::max(1,TfLiteTensorDim(out0,d));
  std::vector<std::pair<float,int>> vals;
  vals.reserve(std::min(outn,100000));
  TfLiteType ot=TfLiteTensorType(out0);
  const void* od=TfLiteTensorData(out0);
  for(int i=0;i<outn && i<100000;i++){
    float v=0;
    if(ot==kTfLiteFloat32) v=((const float*)od)[i];
    else if(ot==kTfLiteUInt8) v=((const uint8_t*)od)[i];
    else if(ot==kTfLiteInt8) v=((const int8_t*)od)[i];
    else if(ot==kTfLiteInt32) v=((const int32_t*)od)[i];
    vals.push_back({v,i});
  }
  std::partial_sort(vals.begin(), vals.begin()+std::min<size_t>(5,vals.size()), vals.end(), [](auto&a,auto&b){return a.first>b.first;});
  std::cout << "{\"ok\":true,\"runtime\":\"tensorflow-lite-c\",\"model\":\""<<jesc(model)<<"\",\"invoke_ms\":"<<ms;
  std::cout << ",\"input\":{\"type\":\""<<tname(TfLiteTensorType(in0))<<"\",\"dims\": [";
  for(int d=0; d<TfLiteTensorNumDims(in0); ++d){ if(d) std::cout<<","; std::cout<<TfLiteTensorDim(in0,d); }
  std::cout << "]},\"output\":{\"type\":\""<<tname(ot)<<"\",\"dims\": [";
  for(int d=0; d<TfLiteTensorNumDims(out0); ++d){ if(d) std::cout<<","; std::cout<<TfLiteTensorDim(out0,d); }
  std::cout << "],\"top\":[";
  for(size_t i=0;i<std::min<size_t>(5,vals.size());++i){ if(i) std::cout<<","; std::cout << "{\"index\":"<<vals[i].second<<",\"score\":"<<vals[i].first<<"}"; }
  std::cout << "]}}\n";
  TfLiteInterpreterDelete(interp); TfLiteInterpreterOptionsDelete(opt); TfLiteModelDelete(m);
  return 0;
}
