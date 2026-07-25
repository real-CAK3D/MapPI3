#!/usr/bin/env python3
"""Pac-Man inspired visual display for an 8x8 Raspberry Pi Sense HAT matrix."""

from __future__ import annotations

import argparse
from collections import deque
import random
import time
from dataclasses import dataclass

try:
    from sense_hat import SenseHat
except ImportError:  # Allows dry runs on machines without Sense HAT installed.
    SenseHat = None


GRID_SIZE = 8

BLACK = (0, 0, 0)
PACMAN = (255, 220, 0)
PACMAN_MOUTH = (0, 0, 0)
FRUIT = (255, 0, 40)
POWERED_PACMAN = (255, 255, 80)
VULNERABLE_GHOST = (30, 30, 255)
EATEN_GHOST = (255, 255, 255)
PACMAN_CAUGHT = (255, 40, 0)
FRUIT_EATEN_POWER_TICKS = 28
GHOST_RESPAWN_TICKS = 10
FRUITS_PER_MAP = 6
GHOST_COLORS = [
    (255, 0, 0),
    (255, 120, 255),
    (0, 220, 255),
    (255, 150, 0),
]


@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def step(self, direction: "Point") -> "Point":
        return Point((self.x + direction.x) % GRID_SIZE, (self.y + direction.y) % GRID_SIZE)


DIRECTIONS = (
    Point(1, 0),
    Point(-1, 0),
    Point(0, 1),
    Point(0, -1),
)


MAP_LAYOUTS = [
    (
        "........",
        ".##..##.",
        "...##...",
        "#..##..#",
        "#......#",
        "...##...",
        ".##..##.",
        "........",
    ),
    (
        "........",
        "..#..#..",
        ".#....#.",
        "...##...",
        "...##...",
        ".#....#.",
        "..#..#..",
        "........",
    ),
    (
        "..####..",
        "........",
        ".##..##.",
        "........",
        "........",
        ".##..##.",
        "........",
        "..####..",
    ),
    (
        "........",
        ".#.#.#..",
        "........",
        "..#..#..",
        "..#..#..",
        "........",
        "..#.#.#.",
        "........",
    ),
]


@dataclass
class Ghost:
    position: Point
    color: tuple[int, int, int]
    direction: Point
    home: Point
    eaten_ticks: int = 0


class InvisibleMaze:
    def __init__(self, layout: tuple[str, ...]) -> None:
        self.layout = layout
        self.cells = {
            Point(x, y)
            for y, row in enumerate(layout)
            for x, value in enumerate(row)
            if value == "."
        }

    def neighbors(self, point: Point) -> list[Point]:
        return [point.step(direction) for direction in DIRECTIONS if point.step(direction) in self.cells]

    def random_cell(self, blocked: set[Point] | None = None) -> Point:
        blocked = blocked or set()
        choices = [point for point in self.cells if point not in blocked]
        return random.choice(choices)


class PacmanDisplay:
    def __init__(self, hat, speed: float, ghosts: int) -> None:
        self.hat = hat
        self.speed = speed
        self.ghost_count = ghosts
        self.map_index = 0
        self.maze = InvisibleMaze(MAP_LAYOUTS[self.map_index])
        self.pacman = Point(0, 0)
        self.pacman_direction = Point(1, 0)
        self.ghosts: list[Ghost] = []
        self.fruit = self._new_fruit()
        self.mouth_open = True
        self.power_ticks = 0
        self.fruits_eaten = 0
        self.caught_flash_ticks = 0
        self._reset_positions()

    def run(self) -> None:
        self.hat.low_light = True
        self.hat.clear()
        try:
            while True:
                self._tick()
                self._draw()
                time.sleep(self.speed)
        except KeyboardInterrupt:
            self.hat.clear()

    def _tick(self) -> None:
        if self.caught_flash_ticks:
            self.caught_flash_ticks -= 1
            if self.caught_flash_ticks == 0:
                self._next_map()
            return

        target = self._nearest_active_ghost() if self.power_ticks else self.fruit
        self.pacman_direction = self._best_direction_to(self.pacman, target)
        self.pacman = self.pacman.step(self.pacman_direction)
        self._handle_collisions()
        if self.caught_flash_ticks:
            return

        if self.pacman == self.fruit:
            self.power_ticks = FRUIT_EATEN_POWER_TICKS
            self.fruits_eaten += 1
            self.fruit = self._new_fruit()
            if self.fruits_eaten % FRUITS_PER_MAP == 0:
                self._next_map()
                return

        for ghost in self.ghosts:
            if ghost.eaten_ticks:
                ghost.eaten_ticks -= 1
                if ghost.eaten_ticks == 0:
                    ghost.position = ghost.home
                continue
            ghost.direction = self._ghost_direction(ghost)
            ghost.position = ghost.position.step(ghost.direction)

        self._handle_collisions()

        self.mouth_open = not self.mouth_open
        self.power_ticks = max(0, self.power_ticks - 1)

    def _draw(self) -> None:
        pixels = [BLACK] * (GRID_SIZE * GRID_SIZE)

        if not self.caught_flash_ticks:
            self._set_pixel(pixels, self.fruit, FRUIT)

        for ghost in self.ghosts:
            if ghost.eaten_ticks:
                if ghost.eaten_ticks % 2 == 0:
                    self._set_pixel(pixels, ghost.position, EATEN_GHOST)
                continue
            color = VULNERABLE_GHOST if self.power_ticks and self.power_ticks % 4 != 0 else ghost.color
            self._set_pixel(pixels, ghost.position, color)

        pacman_color = PACMAN_CAUGHT if self.caught_flash_ticks else POWERED_PACMAN if self.power_ticks else PACMAN
        self._set_pixel(pixels, self.pacman, pacman_color)
        if self.mouth_open and not self.caught_flash_ticks:
            mouth = self.pacman.step(self.pacman_direction)
            if mouth in self.maze.neighbors(self.pacman):
                self._set_pixel(pixels, mouth, PACMAN_MOUTH)

        self.hat.set_pixels(pixels)

    def _new_fruit(self) -> Point:
        blocked = {self.pacman, *(ghost.position for ghost in self.ghosts)}
        return self.maze.random_cell(blocked)

    def _ghost_direction(self, ghost: Ghost) -> Point:
        if self.power_ticks:
            # Frightened ghosts mostly run away, with a little wobble for life.
            if random.random() < 0.75:
                return self._worst_direction_to(ghost.position, self.pacman)
            return self._random_legal_direction(ghost.position, ghost.direction)

        # Mostly chase Pac-Man, sometimes wander so the display stays lively.
        if random.random() < 0.70:
            return self._best_direction_to(ghost.position, self.pacman)
        return self._random_legal_direction(ghost.position, ghost.direction)

    def _best_direction_to(self, start: Point, target: Point) -> Point:
        directions = self._legal_directions(start)
        random.shuffle(directions)
        distances = self._maze_distances(target)
        return min(directions, key=lambda direction: distances.get(start.step(direction), 999))

    def _worst_direction_to(self, start: Point, target: Point) -> Point:
        directions = self._legal_directions(start)
        random.shuffle(directions)
        distances = self._maze_distances(target)
        return max(directions, key=lambda direction: distances.get(start.step(direction), 999))

    def _random_legal_direction(self, start: Point, current: Point) -> Point:
        directions = self._legal_directions(start)
        if current in directions and random.random() < 0.65:
            return current
        return random.choice(directions)

    def _legal_directions(self, start: Point) -> list[Point]:
        directions = [direction for direction in DIRECTIONS if start.step(direction) in self.maze.neighbors(start)]
        return directions or [Point(0, 0)]

    def _maze_distances(self, target: Point) -> dict[Point, int]:
        distances = {target: 0}
        queue = deque([target])
        while queue:
            current = queue.popleft()
            for neighbor in self.maze.neighbors(current):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        return distances

    def _nearest_active_ghost(self) -> Point:
        active_ghosts = [ghost.position for ghost in self.ghosts if not ghost.eaten_ticks]
        if not active_ghosts:
            return self.fruit
        distances = self._maze_distances(self.pacman)
        return min(active_ghosts, key=lambda point: distances.get(point, 999))

    def _handle_collisions(self) -> None:
        for ghost in self.ghosts:
            if ghost.eaten_ticks or ghost.position != self.pacman:
                continue
            if self.power_ticks:
                ghost.eaten_ticks = GHOST_RESPAWN_TICKS
            else:
                self.caught_flash_ticks = 6
                return

    def _next_map(self) -> None:
        self.map_index = (self.map_index + 1) % len(MAP_LAYOUTS)
        self.maze = InvisibleMaze(MAP_LAYOUTS[self.map_index])
        self._reset_positions()

    def _reset_positions(self) -> None:
        cells = sorted(self.maze.cells, key=lambda point: (point.y, point.x))
        self.pacman = cells[0]
        self.pacman_direction = Point(1, 0)
        ghost_homes = list(reversed(cells))
        self.ghosts = [
            Ghost(
                position=ghost_homes[i % len(ghost_homes)],
                color=GHOST_COLORS[i % len(GHOST_COLORS)],
                direction=random.choice(DIRECTIONS),
                home=ghost_homes[i % len(ghost_homes)],
            )
            for i in range(self.ghost_count)
        ]
        self.fruit = self._new_fruit()
        self.power_ticks = 0
        self.caught_flash_ticks = 0

    @staticmethod
    def _wrap_distance(a: Point, b: Point) -> int:
        dx = min(abs(a.x - b.x), GRID_SIZE - abs(a.x - b.x))
        dy = min(abs(a.y - b.y), GRID_SIZE - abs(a.y - b.y))
        return dx + dy

    @staticmethod
    def _set_pixel(pixels: list[tuple[int, int, int]], point: Point, color: tuple[int, int, int]) -> None:
        pixels[point.y * GRID_SIZE + point.x] = color


class ConsoleHat:
    """Tiny console preview for computers without Sense HAT hardware."""

    low_light = True

    def clear(self) -> None:
        print("\033[2J\033[H", end="")

    def set_pixels(self, pixels: list[tuple[int, int, int]]) -> None:
        symbols = {
            BLACK: ".",
            PACMAN: "C",
            PACMAN_MOUTH: ".",
            FRUIT: "o",
            POWERED_PACMAN: "P",
            VULNERABLE_GHOST: "v",
            EATEN_GHOST: "e",
            PACMAN_CAUGHT: "X",
        }
        print("\033[H", end="")
        for y in range(GRID_SIZE):
            row = pixels[y * GRID_SIZE : (y + 1) * GRID_SIZE]
            print(" ".join(symbols.get(pixel, "G") for pixel in row))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animate Pac-Man on an 8x8 Sense HAT LED matrix.")
    parser.add_argument("--speed", type=float, default=0.25, help="Seconds between frames.")
    parser.add_argument("--ghosts", type=int, default=3, choices=[1, 2, 3, 4], help="Number of ghosts.")
    parser.add_argument("--console", action="store_true", help="Preview in the terminal instead of using Sense HAT.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.console:
        hat = ConsoleHat()
    elif SenseHat is None:
        raise SystemExit("sense_hat is not installed. Run on the Pi, or use --console for a text preview.")
    else:
        hat = SenseHat()

    PacmanDisplay(hat, speed=args.speed, ghosts=args.ghosts).run()


if __name__ == "__main__":
    main()
