from __future__ import annotations
import sys
import math
import random
from typing import NamedTuple


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


def spell_control_command(monster: Entity):
    p = get_random_position_in_enemy_base_radius()
    return f'SPELL CONTROL {monster.id} {p.x} {p.y}'


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
                    command = spell_control_command(monster)
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

    nb_defenders = 3
    defenders = my_heroes[:nb_defenders]
    defense_commands = Defense.generate_commands(defenders, monsters, my_mana)


    for command in defense_commands:
        print(command)


    # for i in range(heroes_per_player):
    #     # To debug: print("Debug messages...", file=sys.stderr, flush=True)
