// Pi deploy build: app code only. Big public assets (Herbie art, tiles) already live on the Pi,
// so they are not copied; the few public files that change are uploaded by deploy_web.sh.
import base from '../../vite.config.js';
export default { ...base, build: { ...(base.build || {}), outDir: 'dist-deploy', emptyOutDir: true, copyPublicDir: false } };
