from __future__ import annotations
from ast import Assert
from enum import Enum
import sys
import math
import random
from typing import NamedTuple, Optional


# TODO:
# - I can also send wind and then protect the spider with shield "SPELL SHIELD entityId"

# TODO: TO TRY
# - when attacking, also send some monsters from defense with CONTROL
# - at start of attack, make attacker start from my base, go to enemy base, and on the way, CONTROL all monsters near toward enemy
# - for attacker: try to control some defenders at some point (find the right moment)
# - also attack with WIND. (Find the right time: if when I do it, there will be no defender once the wind is done)
#       Just after that, I should protect the spider.


# TODO: use may new Patroller class in Farming class

class Position(NamedTuple):
    x: int
    y: int


class Entity(NamedTuple):
    id: int
    type: int
    position: Position
    shield_life: int
    is_controlled: int
    health: int
    vx: int
    vy: int
    near_base: int
    threat_for: int


BASE_RADIUS = 5000

TYPE_MONSTER = 0
TYPE_MY_HERO = 1
TYPE_OP_HERO = 2

THREAT_FOR_ME = 1
THREAT_FOR_OP = 2

SPELL_WIND_RADIUS = 1280
SPELL_CONTROL_RANGE = 2200
SPELL_SHIELD_RANGE = 2200
VISION_RANGE = 2200

MANA_PER_SPELL = 10

MAP_SIZE_X = 17630
MAP_SIZE_Y = 9000

# base_x,base_y: The corner of the map representing your base
base_x, base_y = [int(i) for i in input().split()]
heroes_per_player = int(input())

base_position = Position(base_x, base_y)


def get_distance(a: Position, b: Position) -> float:
    return math.sqrt((b.x - a.x)**2 + (b.y - a.y)**2)


def bound_to_zero_one(x: int) -> float:
    """
    increasing function
    result bounded to ]0-1]
    """
    return 1 - 1/(1 + x)


def invert_position(position: Position):
    """
    If this method takes my base position as input, it returns the enemy base position.
    """
    return Position(
        MAP_SIZE_X - position.x,
        MAP_SIZE_Y - position.y)


enemy_base_position = invert_position(base_position)


def get_random_position_in_enemy_base_radius():
    angles = [math.pi / 2 / 8, math.pi / 4, 7 * math.pi / 2 / 8]
    # angle = random.uniform(0, math.pi / 2)
    angle = random.choice(angles)
    p = Position(
            int(BASE_RADIUS * math.cos(angle)),
            int(BASE_RADIUS * math.sin(angle)))
    if base_position.x == 0:
        p = invert_position(p)

    return p


def move_to_target_command(target: Position, comment: str = ''):
    return f"MOVE {target.x} {target.y} {comment}"


def spell_wind_command(comment: str = ''):
    return f'SPELL WIND {enemy_base_position.x} {enemy_base_position.y} {comment}'


def spell_control_command(monster: Entity, use_random_position: bool):
    if use_random_position:
        p = get_random_position_in_enemy_base_radius()
    else:
        p = enemy_base_position
    return f'SPELL CONTROL {monster.id} {p.x} {p.y}'


def spell_shield_command(entity: Entity) -> str:
    return f'SPELL SHIELD {entity.id}'


###### DEFENSE ##############


class Defense:

    @staticmethod
    def get_waiting_positions(nb_positions: int, radius: float = BASE_RADIUS * 1.2):
        base_angle = math.pi / 2 / (nb_positions + 1)
        angles = [i * base_angle for i in range(1, nb_positions + 1)]  # Angles in degrees

        positions = []
        for angle in angles:
            p = Position(
                int(radius * math.cos(angle)),
                int(radius * math.sin(angle)))

            if base_position.x > 0:
                p = invert_position(p)
            positions.append(p)

        return positions


    @staticmethod
    def move_to_waiting_position(hero_index: int, nb_defenders: int):
        """
        hero_index should be between 0 and nb_heroes - 1
        """
        waiting_positions = Defense.get_waiting_positions(nb_defenders)
        position = waiting_positions[hero_index]
        return move_to_target_command(position, comment='moving to waiting defense position')


    @staticmethod
    def get_threat_level(monster: Entity) -> float:
        threat_level: float = 0
        if monster.threat_for == THREAT_FOR_ME:
            if monster.near_base:
                threat_level += 1000
            else:
                threat_level += 500

        distance_to_base = get_distance(monster.position, base_position)

        threat_level += 500 / (1 + distance_to_base)

        # TODO: see if this is a good idea: we don't want to attack spiders too far
        # The risk is that if defense goes to far, it doesn't have enough time to come back to base in case of attack
        if distance_to_base > 1.5 * BASE_RADIUS:
            threat_level = 0

        if monster.threat_for == THREAT_FOR_OP:
            return 0  # We don't want to attack spiders if there are directed to enemy base

        return threat_level


    @staticmethod
    def find_targets(monsters: list[Entity]):
        monsters_with_threat_level = [
            (monster, Defense.get_threat_level(monster))
            for monster in monsters
        ]

        # Do not consider targets with threat_level=0
        potential_targets = [
            (monster, threat_level) for (monster, threat_level) in monsters_with_threat_level
            if threat_level > 0]

        # Sort monsters by descending threat level
        potential_targets.sort(key=lambda x: x[1], reverse=True)
        return [monster for (monster, _) in potential_targets]


    @staticmethod
    def assign_heroes_to_monsters(heroes: list[Entity], ordered_monsters: list[Entity]):
        """
        heroes: only defenders
        """
        # For each of these monsters, we want to attack with the closest hero
        hero_to_monster: dict[int, int] = {}

        for monster in ordered_monsters:
            remaining_heroes = [
                hero for hero in heroes
                if hero.id not in hero_to_monster and not hero.is_controlled
            ]
            if remaining_heroes:
                chosen_hero = min(remaining_heroes, key=lambda x: get_distance(x.position, monster.position))
                hero_to_monster[chosen_hero.id] = monster.id

        return hero_to_monster


    @staticmethod
    def should_use_shield_spell(hero: Entity, opp_heroes: list[Entity], enemy_tries_control: bool, my_mana: int):
        if enemy_tries_control and opp_heroes:
            d_hero_opp = min([get_distance(hero.position, opp_hero.position) for opp_hero in opp_heroes])

            return (
                hero.shield_life == 0
                and my_mana >= 3 * MANA_PER_SPELL
                and d_hero_opp <= SPELL_CONTROL_RANGE) # an opponent hero could take control

        return False


    @staticmethod
    def should_use_wind_spell(monster: Entity, hero: Entity, my_mana: int):
        distance_to_hero = get_distance(monster.position, hero.position)
        distance_to_base = get_distance(monster.position, base_position)

        # False if it's not possible cast the spell
        if (monster.shield_life > 0
            or distance_to_hero >= SPELL_WIND_RADIUS
            or my_mana < MANA_PER_SPELL):
            return False

        if (my_mana > 3 * MANA_PER_SPELL):
            # we have tons of mana, let's use it!
            return distance_to_base < BASE_RADIUS  # inside base radius
        else:
            return distance_to_base < BASE_RADIUS / 3  # very close to base


    @staticmethod
    def should_use_control_spell(monster: Entity, hero: Entity, my_mana: int):
        # disabling control spell
        return False
        distance_to_hero = get_distance(monster.position, hero.position)
        distance_to_base = get_distance(monster.position, base_position)
        distance_to_enemy_base = get_distance(monster.position, enemy_base_position)

        return (
            my_mana > MANA_PER_SPELL * 3 # we want to keep some mana if need for defense with WIND
            and monster.shield_life == 0  # monster not protected by a shield
            and distance_to_base > BASE_RADIUS # monster outside my base radius: it will directly send it to enemy base
            and distance_to_enemy_base > 1.5 * BASE_RADIUS # if it's close to enemy base, it's better to use a wind spell
            and distance_to_hero < SPELL_CONTROL_RANGE
            and monster.threat_for != THREAT_FOR_OP
        )

    @staticmethod
    def __get_commands(
        hero_to_monster: dict[int, int],
        heroes: list[Entity],
        monsters_by_id: dict[int, Entity],
        opp_heroes: list[Entity],
        enemy_tries_control: bool,
        my_mana: int
    ) -> list[str]:
        """
        heroes: only the defenders
        """
        commands = []
        for (i, hero) in enumerate(heroes):
            if Defense.should_use_shield_spell(hero, opp_heroes, enemy_tries_control, my_mana):
                command = spell_shield_command(hero)
            elif hero.id in hero_to_monster:
                monster_id = hero_to_monster[hero.id]
                monster = monsters_by_id[monster_id]

                # TODO: update when we should use the spell
                if Defense.should_use_wind_spell(monster, hero, my_mana):
                    command = spell_wind_command(comment=f'for monster {monster.id}')
                    my_mana -= MANA_PER_SPELL
                elif Defense.should_use_control_spell(monster, hero, my_mana):
                    command = spell_control_command(monster, use_random_position=True)
                    my_mana -= MANA_PER_SPELL
                else:
                    command = move_to_target_command(monster.position, f"to monster {monster.id}")
            else:
                command = Defense.move_to_waiting_position(i, len(heroes))
                # command = "WAIT"
            commands.append(command)

        return commands


    @staticmethod
    def generate_commands(
        heroes: list[Entity],
        monsters: list[Entity],
        opp_heroes: list[Entity],
        enemy_tries_control: bool,
        my_mana: int
    ) -> list[str]:
        monsters_to_attack = Defense.find_targets(monsters)
        hero_to_monster = Defense.assign_heroes_to_monsters(heroes, monsters_to_attack)

        monsters_by_id = {m.id: m for m in monsters}
        return Defense.__get_commands(hero_to_monster, heroes, monsters_by_id, opp_heroes, enemy_tries_control, my_mana)


class Patroller:

    def __init__(self, patrol_positions: list[Position], infinite_loop: bool) -> None:
        Assert(len(patrol_positions) > 0)
        self._patrol_positions = patrol_positions
        self._infinite_loop = infinite_loop
        self._current_patrol_idx = 0
        self._is_finished = False

    def is_finished(self, hero: Entity):
        if self._current_patrol_idx == len(self._patrol_positions) - 1:
            # last position
            current_patrol_position = self._patrol_positions[self._current_patrol_idx]
            d = get_distance(hero.position, current_patrol_position)
            if d < 800:
                self._is_finished = True

        return self._is_finished


    def next_position_for_patrol(self, hero: Entity) -> Position:
        current_patrol_position = self._patrol_positions[self._current_patrol_idx]

        d = get_distance(hero.position, current_patrol_position)

        if (d < 800):
            # we're close to the position, we can now go to the next one
            self._current_patrol_idx += 1

            if self._infinite_loop:
                self._current_patrol_idx = self._current_patrol_idx % len(self._patrol_positions)
            else:
                if self._current_patrol_idx >= len(self._patrol_positions):
                    # We reached the end, we keep the same target and set is_finished to True
                    self._is_finished = True
                    self._current_patrol_idx = len(self._patrol_positions) - 1

        return self._patrol_positions[self._current_patrol_idx]


class Farming:
    # Move in the middle of the map, and attack all available monsters

    def __init__(self) -> None:
        patrol_positions = [
            Position(int(MAP_SIZE_X/2), int(MAP_SIZE_Y * 0.2)),
            Position(int(MAP_SIZE_X/2), int(MAP_SIZE_Y * 0.8))
        ]
        self._patroller = Patroller(patrol_positions, infinite_loop=True)


    @staticmethod
    def is_inside_area(position: Position):
        # not too close to neither base
        distance_to_base = get_distance(position, base_position)
        distance_to_enemy_base = get_distance(position, enemy_base_position)

        return (
            distance_to_base > 1.5 * BASE_RADIUS
            and distance_to_enemy_base > 1.5 * BASE_RADIUS)


    @staticmethod
    def get_target(hero: Entity, monsters: list[Entity]) -> Optional[Entity]:
        """
        closest monster in area
        """
        targets = [m for m in monsters if Farming.is_inside_area(m.position)]
        if targets:
            return min(targets, key=lambda x: get_distance(x.position, hero.position))

        return None


    def get_command(self, hero: Entity, monsters: list[Entity]) -> str:
        target = Farming.get_target(hero, monsters)
        if target:
            return move_to_target_command(target.position, f'farmer->m{target.id}')

        next_position = self._patroller.next_position_for_patrol(hero)
        return move_to_target_command(next_position, 'farmer->patrol')


class Attacking:

    @staticmethod
    def get_waiting_position():
        angle = math.pi / 8
        radius = 1.1 * BASE_RADIUS
        p = Position(
            int(radius * math.cos(angle)),
            int(radius * math.sin(angle)))

        # We want a point close to the enemy base
        if base_position.x == 0:
            p = invert_position(p)

        return p


    @staticmethod
    def get_potential_shield_actions(
        hero: Entity,
        monsters: list[Entity],
        my_mana: int,
        only_in_hero_range: bool
    ) -> list[tuple[str, Entity, float]]:
        actions: list[tuple[str, Entity, float]] = []

        for monster in monsters:
            d_hero_monster = get_distance(hero.position, monster.position)
            d_monster_enemy_base = get_distance(monster.position, enemy_base_position)

            if (my_mana <= 3 * MANA_PER_SPELL  # We want to keep mana for defense in case it's needed
                or monster.shield_life > 0  # can't SHIELD a monster with SHIELD
                or monster.threat_for != THREAT_FOR_OP):  # we only want to SHIELD monsters attacking opponent base
                continue
            if (only_in_hero_range and d_hero_monster >= SPELL_SHIELD_RANGE):  # too far away
                continue

            # TODO: reevaluate this condition + score
            if d_monster_enemy_base < 1.1 * BASE_RADIUS:
                score = 1000 + 10 * bound_to_zero_one(monster.health)
                action = spell_shield_command(monster)
                actions.append((action, monster, score))

        return actions


    @staticmethod
    def get_potential_control_actions(
        hero: Entity,
        monsters: list[Entity],
        my_mana: int,
        only_in_hero_range: bool
    ) -> list[tuple[str, Entity, float]]:
        actions: list[tuple[str, Entity, float]] = []

        for monster in monsters:
            d_hero_monster = get_distance(hero.position, monster.position)
            d_monster_enemy_base = get_distance(monster.position, enemy_base_position)

            if (my_mana <= 3 * MANA_PER_SPELL  # We want to keep mana for defense in case it's needed
                or monster.shield_life > 0  # We can't CONTROL a monster with SHIELD
                or monster.threat_for == THREAT_FOR_OP):  # we only want to CONTROL monsters not attacking opponent base
                continue

            if (only_in_hero_range and d_hero_monster >= SPELL_SHIELD_RANGE):  # too far away
                continue

            # TODO: reevaluate this condition + score
            if d_monster_enemy_base < 1.5 * BASE_RADIUS:
                score = 500 + 10 * bound_to_zero_one(monster.health)
                action = spell_control_command(monster, use_random_position=False)
                actions.append((action, monster, score))

        return actions


    @staticmethod
    def get_move_command(hero: Entity, monsters: list[Entity], my_mana: int) -> str:
        potential_spells = (
            Attacking.get_potential_control_actions(hero, monsters, my_mana, only_in_hero_range=False)
            + Attacking.get_potential_shield_actions(hero, monsters, my_mana, only_in_hero_range=False)
        )

        if potential_spells:
            best_spell = max(potential_spells, key=lambda x: x[2])  # best score
            spell_command, entity, score = best_spell
            return move_to_target_command(entity.position)
        else:
            waiting_position = Attacking.get_waiting_position()
            return move_to_target_command(waiting_position, 'att->waiting')


    @staticmethod
    def get_command(hero: Entity, monsters: list[Entity], my_mana: int) -> str:

        d = get_distance(hero.position, enemy_base_position)
        if (d > 1.5 * BASE_RADIUS):
            waiting_position = Attacking.get_waiting_position()
            return move_to_target_command(waiting_position, 'att->position')

        potential_spells = (
            Attacking.get_potential_control_actions(hero, monsters, my_mana, only_in_hero_range=True)
            + Attacking.get_potential_shield_actions(hero, monsters, my_mana, only_in_hero_range=True)
        )

        if potential_spells:
            best_spell = max(potential_spells, key=lambda x: x[2])  # best score
            spell_command, entity, score = best_spell
            return spell_command
        else:
            return Attacking.get_move_command(hero, monsters, my_mana)

        # TODO: go over enemies and see:
        # - if I could CONTROL one


class BeforeAttacking:
    """
    This will be used between the FARMING step and the ATTACKING step.
    The idea is to go over the map, and send monsters to enemy base with CONTROL
    """

    STEP_TO_STARTING_POSITION = 'STEP_TO_STARTING_POSITION'
    STEP_TO_ENEMY_POSITION = 'STEP_TO_ENEMY_POSITION'

    def __init__(self) -> None:
        starting_position = Position(VISION_RANGE, MAP_SIZE_Y - VISION_RANGE)  # Bottom left
        ending_position = Position(int(MAP_SIZE_X - 1.3 * BASE_RADIUS), MAP_SIZE_Y - VISION_RANGE) # Bottom right, near base radius
        # adapt position if our base is not on Top left
        if base_position.x > 0:
            starting_position = invert_position(starting_position)
            ending_position = invert_position(ending_position)

        self._start_patroller = Patroller([starting_position], infinite_loop=False)
        self._to_enemy_patroller = Patroller([ending_position], infinite_loop=False)
        self.is_step_finished = False
        self._current_step = self.STEP_TO_STARTING_POSITION


    def _update_step(self, hero):
        if self._current_step == self.STEP_TO_STARTING_POSITION:
            if self._start_patroller.is_finished(hero):
                self._current_step = self.STEP_TO_ENEMY_POSITION

        elif self._current_step == self.STEP_TO_ENEMY_POSITION:
            if self._to_enemy_patroller.is_finished(hero):
                self.is_step_finished = True

    @staticmethod
    def _get_potential_monster_to_control(hero: Entity, monsters: list[Entity], my_mana: int) -> Optional[Entity]:
        potential_monsters: list[Entity] = []
        for monster in monsters:
            d_hero_monster = get_distance(hero.position, monster.position)
            if (monster.threat_for != THREAT_FOR_OP
                and monster.shield_life == 0
                and my_mana > 10 * MANA_PER_SPELL
                and d_hero_monster < SPELL_CONTROL_RANGE):
                potential_monsters.append(monster)

        if potential_monsters:
            # if multiple monsters, take the one with most health
            return max(potential_monsters, key=lambda x: x.health)

        return None


    def get_command(self, hero: Entity, monsters: list[Entity], my_mana: int) -> str:
        self._update_step(hero)

        if self._current_step == self.STEP_TO_STARTING_POSITION:
            next_position = self._start_patroller.next_position_for_patrol(hero)
            return move_to_target_command(next_position, 'ba->to start')

        elif self._current_step == self.STEP_TO_ENEMY_POSITION:
            monster_to_control = BeforeAttacking._get_potential_monster_to_control(hero, monsters, my_mana)
            if monster_to_control:
                return spell_control_command(monster_to_control, use_random_position=False)
            else:
                next_position = self._to_enemy_patroller.next_position_for_patrol(hero)
                return move_to_target_command(next_position, 'ba->to enemy')
        else:
            raise Exception(f'Unsupported step: {self._current_step}')


class Strategy(Enum):
    FARMING = 1
    BEFORE_ATTACKING = 2
    ATTACKING = 3


class Orchestrator:
    """
    Decides which type of strategy (defense/farming/attack) should be applied during the game

    FARMING -> BEFORE_ATTACKING -> ATTACKING
    """
    # TODO: adapt this number
    MANA_THRESHOLD_FOR_ATTACK = 22 * MANA_PER_SPELL
    # TODO: adapt this number
    MANA_THRESHOLD_FOR_FARMING = 3 * MANA_PER_SPELL

    # Don't start attacking before that frame.
    # That way, when we start the attack, there are already some big monsters
    MIN_GAME_FRAME_FOR_ATTACK = 95

    def __init__(self) -> None:
        # Start game by farming
        self._current_strategy = Strategy.FARMING
        self._farming = Farming()
        self._before_attacking = BeforeAttacking()
        self._enemy_tries_control = False
        self._game_frame = 0


    def _update_strategy(self, my_mana: int):
        # if we have enough mana, switch to attack preparation
        if (my_mana > self.MANA_THRESHOLD_FOR_ATTACK
            and self._current_strategy == Strategy.FARMING
            and self._game_frame >= self.MIN_GAME_FRAME_FOR_ATTACK
        ):
            print("Switching to Strategy.BEFORE_ATTACKING", file=sys.stderr, flush=True)
            self._current_strategy = Strategy.BEFORE_ATTACKING

        elif (self._current_strategy == Strategy.BEFORE_ATTACKING and self._before_attacking.is_step_finished):
            # we've finished the BEFORE_ATTACKING step and reached enemy base
            self._current_strategy = Strategy.ATTACKING

        # if low mana, go farming
        elif (my_mana < self.MANA_THRESHOLD_FOR_FARMING and self._current_strategy != Strategy.FARMING):
            print("Switching to Strategy.FARMING", file=sys.stderr, flush=True)
            self._current_strategy = Strategy.FARMING


    def get_commands(
        self,
        heroes: list[Entity],
        monsters: list[Entity],
        opp_heroes: list[Entity],
        my_mana: int
    ) -> list[str]:

        self._game_frame += 1
        self._update_strategy(my_mana)

        for hero in heroes:
            if hero.is_controlled:
                self._enemy_tries_control = True

        if self._current_strategy == Strategy.FARMING:
            # 2 defenders + 1 farmer
            nb_defenders = 2
            defenders = heroes[:nb_defenders]
            defense_commands = Defense.generate_commands(defenders, monsters, opp_heroes, self._enemy_tries_control, my_mana)

            farmer_command = self._farming.get_command(heroes[nb_defenders], monsters)
            return defense_commands + [farmer_command]

        elif self._current_strategy == Strategy.BEFORE_ATTACKING:
            # 2 defenders + 1 attacker
            nb_defenders = 2
            defenders = heroes[:nb_defenders]
            defense_commands = Defense.generate_commands(defenders, monsters, opp_heroes, self._enemy_tries_control, my_mana)

            attacker_command = self._before_attacking.get_command(heroes[nb_defenders], monsters, my_mana)
            return defense_commands + [attacker_command]

        elif self._current_strategy == Strategy.ATTACKING:
            # 2 defenders + 1 attacker
            nb_defenders = 2
            defenders = heroes[:nb_defenders]
            defense_commands = Defense.generate_commands(defenders, monsters, opp_heroes, self._enemy_tries_control, my_mana)
            attack_command = Attacking.get_command(heroes[nb_defenders], monsters, my_mana)
            return defense_commands + [attack_command]

        else:
            raise Exception(f'Unhandled strategy: {self._current_strategy}')


orchestrator = Orchestrator()

# game loop
while True:
    my_health, my_mana = [int(j) for j in input().split()]
    enemy_health, enemy_mana = [int(j) for j in input().split()]
    entity_count = int(input())  # Amount of heros and monsters you can see

    monsters = []
    my_heroes = []
    opp_heroes = []
    for i in range(entity_count):
        _id, _type, x, y, shield_life, is_controlled, health, vx, vy, near_base, threat_for = [int(j) for j in input().split()]
        entity = Entity(
            _id,            # _id: Unique identifier
            _type,          # _type: 0=monster, 1=your hero, 2=opponent hero
            Position(x, y), # Position of this entity
            shield_life,    # shield_life: Ignore for this league; Count down until shield spell fades
            is_controlled,  # is_controlled: Ignore for this league; Equals 1 when this entity is under a control spell
            health,         # health: Remaining health of this monster
            vx, vy,         # vx,vy: Trajectory of this monster
            near_base,      # near_base: 0=monster with no target yet, 1=monster targeting a base
            threat_for      # threat_for: Given this monster's trajectory, is it a threat to 1=your base, 2=your opponent's base, 0=neither
        )

        if _type == TYPE_MONSTER:
            monsters.append(entity)
        elif _type == TYPE_MY_HERO:
            my_heroes.append(entity)
        elif _type == TYPE_OP_HERO:
            opp_heroes.append(entity)


    commands = orchestrator.get_commands(my_heroes, monsters, opp_heroes, my_mana)

    for command in commands:
        print(command)


    # To debug: print("Debug messages...", file=sys.stderr, flush=True)
