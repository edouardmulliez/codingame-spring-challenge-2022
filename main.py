from __future__ import annotations
from email.mime import base
import sys
import math
import random
from typing import NamedTuple, Optional


# TODO:
# - I should not use wind spell if the target is protected by a shield: DONE
# - make my defense wait close to my base radius: DONE
# - I can send spiders which are going to enter in my zone towards to enemy base "SPELL CONTROL entityId x y" : DONE
# - avoid sending my defense too far away: DONE
# For attack: I can send 1 hero toward enemy base
# - I could try to attack opponents (go next to their base and send them spiders) "SPELL WIND x y"
# - I can also send wind and then protect the spider with shield "SPELL SHIELD entityId"

# I want 2 defenders + 1 farmer


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
        nb_heroes = len(heroes)
        # Only try to attack at most the first nb_heroes monsters
        ordered_monsters = ordered_monsters[:nb_heroes]

        # For each of these monsters, we want to attack with the closest hero
        hero_to_monster: dict[int, int] = {}

        for monster in ordered_monsters:
            remaining_heroes = [hero for hero in heroes if hero.id not in hero_to_monster]
            chosen_hero = min(remaining_heroes, key=lambda x: get_distance(x.position, monster.position))
            hero_to_monster[chosen_hero.id] = monster.id

        return hero_to_monster


    @staticmethod
    def should_use_wind_spell(monster: Entity, hero: Entity, my_mana: int):
        distance_to_hero = get_distance(monster.position, hero.position)
        distance_to_base = get_distance(monster.position, base_position)

        # False if it's not possible cast the spell
        if (monster.shield_life > 0
            or distance_to_hero >= SPELL_WIND_RADIUS
            or my_mana < MANA_PER_SPELL):
            return False

        if (my_mana > 10 * MANA_PER_SPELL):
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
        my_mana: int
    ) -> list[str]:
        """
        heroes: only the defenders
        """
        commands = []
        for (i, hero) in enumerate(heroes):
            if hero.id in hero_to_monster:
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
    def generate_commands(heroes: list[Entity], monsters: list[Entity], my_mana: int) -> list[str]:
        monsters_to_attack = Defense.find_targets(monsters)
        hero_to_monster = Defense.assign_heroes_to_monsters(heroes, monsters_to_attack)

        monsters_by_id = {m.id: m for m in monsters}
        return Defense.__get_commands(hero_to_monster, heroes, monsters_by_id, my_mana)


class Farming:

    # Idea: define a zone where the hero should attack all monsters
    # - Let's start with a square
    # - he should attack the monster closest to him inside the square
    # - if no monster, he should patrol / or come to waiting position for start

    patrol_positions = [
        Position(int(MAP_SIZE_X/2), int(MAP_SIZE_Y * 0.2)),
        Position(int(MAP_SIZE_X/2), int(MAP_SIZE_Y * 0.8))
    ]

    def __init__(self) -> None:
        self.current_patrol_idx = 0


    @staticmethod
    def is_inside_area(position: Position):
        # not too close to neither base
        distance_to_base = get_distance(position, base_position)
        distance_to_enemy_base = get_distance(position, enemy_base_position)

        return (
            distance_to_base > 1.5 * BASE_RADIUS
            and distance_to_enemy_base > 1.5 * BASE_RADIUS)


    def next_position_for_patrol(self, hero: Entity) -> Position:
        current_patrol_position = self.patrol_positions[self.current_patrol_idx]

        d = get_distance(hero.position, current_patrol_position)

        if (d < 100):
            # we're close to the position, we can now go to the next one
            self.current_patrol_idx = (self.current_patrol_idx + 1) % len(self.patrol_positions)

        return self.patrol_positions[self.current_patrol_idx]


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

        next_position = self.next_position_for_patrol(hero)
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

            if (my_mana <= 5 * MANA_PER_SPELL  # We want to keep mana for defense in case it's needed
                or monster.shield_life > 0  # can't SHIELD a monster with SHIELD
                or monster.threat_for != THREAT_FOR_OP):  # we only want to SHIELD monsters attacking opponent base
                continue
            if (only_in_hero_range and d_hero_monster >= SPELL_SHIELD_RANGE):  # too far away
                continue

            # TODO: reevaluate this condition + score
            if d_monster_enemy_base < 1.2 * BASE_RADIUS:
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

            if (my_mana <= 5 * MANA_PER_SPELL  # We want to keep mana for defense in case it's needed
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

        # TODO: make a list of possible action (entity (can be monster or enemy), TYPE(shield, control,...))
        # For each action, assign a score
        # Do action with highest score

        # TODO: go over enemies and see:
        # - if I could CONTROL one


farming = Farming()

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

    # 2 defenders + 1 farmer
    nb_defenders = 2
    defenders = my_heroes[:nb_defenders]
    defense_commands = Defense.generate_commands(defenders, monsters, my_mana)

    farmer_command = farming.get_command(my_heroes[nb_defenders], monsters)

    for command in defense_commands:
        print(command)

    print(farmer_command)

    # for i in range(heroes_per_player):
    #     # To debug: print("Debug messages...", file=sys.stderr, flush=True)
