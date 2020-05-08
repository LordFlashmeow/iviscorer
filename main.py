import sys
from typing import Dict
from datetime import datetime

import auraxium

# Query user for username if none is specified in the command line
if len(sys.argv) == 1:
    character_name = input("Enter a character name: ")

else:
    character_name = sys.argv[1]


class PlayerClass:
    profile_id_dict = {1: 'Infiltrator', 3: 'Light Assault', 4: 'Medic', 5: 'Engineer',
                       6: 'Heavy Assault',
                       7: 'MAX'}

    def __init__(self, loadout_id=0, profile_id=0, kills=0, headshots=0, hits=0, hits_forever=0, shots_fired=0,
                 shots_fired_forever=0):
        self.loadout_id = loadout_id
        self.kills = kills
        self.headshots = headshots
        self.hits = hits
        self.hits_forever = hits_forever
        self.shots_fired = shots_fired
        self.shots_fired_forever = shots_fired_forever
        self.profile_id = profile_id

        self.class_name = self.generate_class_name()

    def generate_class_name(self):
        """
        Sets and returns the class name based on the existing profile id

        :return str: The name of the class
        """
        self.class_name = self.profile_id_dict[self.profile_id]
        return self.class_name

    @staticmethod
    def loadout_to_profile_id(loadout_id):
        """
        Converts a loadout id (1-20) to a profile id (1-7)

        :param int loadout_id: The id to convert
        :return: a profile_id
        :rtype: int
        """

        if loadout_id < 8:  # NC loadouts have the same values as profiles
            return int(loadout_id)

        else:  # TR and VS are shifted over by 7
            id = int(loadout_id) % 7

            # Loadouts start at 1, so MAXes are multiples of 7 starting at 7.
            # Modulo will return 0 instead of 7, so we make a special case for it
            if id == 0:
                return 7

            return id

    def __contains__(self, item):
        """Returns if the profile id matches the item"""
        if item == self.profile_id:
            return True

    def __str__(self):
        return "Class: %s  %d shots %d hits %d kills  %d headshots" % (
            self.class_name, self.shots_fired, self.hits, self.kills, self.headshots)

    def __repr__(self):
        return "Class: %s  %d shots %d hits %d kills  %d headshots" % (
            self.class_name, self.shots_fired, self.hits, self.kills, self.headshots)


character_id_query = auraxium.Query('character_name', namespace='ps2', name__first_lower=character_name.lower())

character_id_results = character_id_query.get()

character_id = character_id_results[0]['character_id']

# Get class accuracy
# http://census.daybreakgames.com/get/ps2/character/5428359100720207121?c:join=characters_stat^on:character_id^to:character_id^list:1^inject_at:stats
class_accuracy = auraxium.Query('character', character_id=character_id).set_show_fields('character_id')
class_accuracy.join('characters_stat', on='character_id', to='character_id', is_list=True, inject_at='stats')

class_accuracy = class_accuracy.get()

class_stats: Dict[int, PlayerClass] = {}

# item^on:attacker_weapon_id^to:item_id^terms:item_type_id=26'item_category_id=<100^outer:0^show:name.en
recent_kills = auraxium.Query('characters_event', namespace='ps2', character_id=character_id, limit=500,
                              type="KILL")
recent_kills.join('item', on='attacker_weapon_id', to='item_id', item_type_id=26, attacker_vehicle_id=0,
                  item_category_id='<100',
                  is_outer=False, show=['name.en'])

loadouts = {15: 'Infiltrator', 17: 'Light Assault', 18: 'Medic', 19: 'Engineer', 20: 'Heavy Assault', 21: 'MAX'}

recent_kills_result = recent_kills.get()

# Find time difference between first and last kill - apply monthly accuracy scores if kills happened over the last month
# and weekly scores if kills happened over the last week
# Switching points are: <= 1.5 days: daily, <= 1.5 weeks: weekly, <= 1.5 months: monthly, older:forever

oldest_kill = recent_kills_result[-1]['timestamp']
newest_kill = recent_kills_result[0]['timestamp']

timeframe = ""

if newest_kill - oldest_kill <= 129600:
    timeframe = "daily"

elif newest_kill - oldest_kill <= 907200:
    timeframe = 'weekly'

elif newest_kill - oldest_kill <= 3888000:
    timeframe = 'monthly'

else:
    timeframe = 'forever'

for stat in class_accuracy[0]['stats']:  # TODO pick item more intelligently, maybe class_accuracy.index('stats')
    profile_id = stat['profile_id']
    if stat['stat_name'] == 'hit_count':
        if profile_id in class_stats:
            class_stats[profile_id].hits = stat['value_' + timeframe]
            class_stats[profile_id].hits_forever = stat['value_forever']

        else:
            class_stats[profile_id] = PlayerClass(profile_id=profile_id, hits=stat['value_' + timeframe], hits_forever=stat['value_forever'])

    if stat['stat_name'] == 'fire_count':
        if profile_id in class_stats:
            class_stats[profile_id].shots_fired = stat['value_' + timeframe]
            class_stats[profile_id].shots_fired_forever = stat['value_forever']


        else:
            class_stats[profile_id] = PlayerClass(profile_id=profile_id, shots_fired=stat['value_' + timeframe], shots_fired_forever=stat['value_forever'])

for kill in recent_kills_result:
    profile_id = PlayerClass.loadout_to_profile_id(kill['attacker_loadout_id'])

    # Skip any vehicle kills that sneak through
    if kill['attacker_vehicle_id'] != 0:
        continue

    if kill['is_headshot'] == 1:
        class_stats[profile_id].headshots += 1

    class_stats[profile_id].kills += 1

total_shots_fired = 0
total_hits = 0
total_kills = 0
total_headshots = 0

print("Player: ", character_id_results[0]['name']['first'])
print("Kills since: ", datetime.utcfromtimestamp(oldest_kill).strftime('%Y-%m-%d %H:%M'))


# Generate weekly/monthly stats
for profile_id, class_data in class_stats.items():
    try:
        # Do these first, so that the stats don't get added if there were no shots in the timeframe
        accuracy = (class_data.hits / class_data.shots_fired) * 100
        hsr = (class_data.headshots / class_data.kills) * 100

        total_shots_fired += class_data.shots_fired
        total_hits += class_data.hits
        total_kills += class_data.kills
        total_headshots += class_data.headshots

        ivi = accuracy * hsr
        if ivi == 0:
            continue

        print("Class: %s - IvI: %d - ACC: %f - HSR: %f - HS: %d Kill: %d" % (
            class_data.class_name, accuracy * hsr, accuracy, hsr, class_data.headshots, class_data.kills))
    except ZeroDivisionError:
        continue

print("Your overall %s accuracy IvI is: %d" % (
    timeframe, (total_hits / total_shots_fired) * (total_headshots / total_kills) * 10000))

# Generate forever stats
if timeframe != 'forever':

    print('\nStats using all-time accuracy data')

    total_shots_fired = 0
    total_hits = 0

    for profile_id, class_data in class_stats.items():
        try:
            total_shots_fired += class_data.shots_fired_forever
            total_hits += class_data.hits_forever

            accuracy = (class_data.hits_forever / class_data.shots_fired_forever) * 100
            hsr = (class_data.headshots / class_data.kills) * 100

            ivi = accuracy * hsr
            if ivi == 0:
                continue

            print("Class: %s - IvI: %d - ACC: %f - HSR: %f - HS: %d Kill: %d" % (
                class_data.class_name, accuracy * hsr, accuracy, hsr, class_data.headshots, class_data.kills))
        except ZeroDivisionError:
            continue

    print("Your overall forever accuracy IvI is: %d" % (
        (total_hits / total_shots_fired) * (total_headshots / total_kills) * 10000))
