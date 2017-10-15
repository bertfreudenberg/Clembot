import os
import sys
import tempfile
import asyncio
import gettext
import re
import pickle
import json
import time
import datetime
import copy
from time import strftime
import logging
import discord
from discord.ext import commands
import spelling
from PIL import Image
from PIL import ImageFilter
from PIL import ImageEnhance
import pytesseract
import requests
from io import BytesIO
import checks
import hastebin
#---- dependencies
import time
from datetime import tzinfo, timedelta, datetime
import pytz
from pytz import timezone

tessdata_dir_config = "--tessdata-dir 'C:\\Program Files (x86)\\Tesseract-OCR\\tessdata' "
xtraconfig = "-l eng -c tessedit_char_blacklist=&|=+%#^*[]{};<> -psm 6"

if os.name == 'nt':
    tesseract_config = tessdata_dir_config + xtraconfig
else:
    tesseract_config = xtraconfig

formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
def setup_logger(name, log_file, level):

    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

try:
    os.makedirs("logs")
except OSError as exception:
    pass

try:
    os.remove('logs/clembot_backup.log')
except OSError as e:
    pass

try:
    os.rename('logs/clembot.log', 'logs/clembot_backup.log')
except OSError:
    pass

logger = setup_logger('discord','logs/clembot.log',logging.INFO)



Clembot = commands.Bot(command_prefix="!")

with open("serverdict", "rb") as fd:
    Clembot.server_dict = pickle.load(fd)
    server_dict = Clembot.server_dict

config = {}
pkmn_info = {}
type_chart = {}
type_list = []
raid_info = {}
active_raids = []

# Append path of this script to the path of
# config files which we're loading.
# Assumes that config files will always live in the same directory.
script_path = os.path.dirname(os.path.realpath(__file__))

def load_config():
    global config
    global pkmn_info
    global type_chart
    global type_list
    global raid_info

    # Load configuration
    with open(os.path.join(script_path, "config.json"), "r") as fd:
        config = json.load(fd)

    # Set up message catalog access
    language = gettext.translation('clembot', localedir='locale', languages=[config['bot-language']])
    language.install()
    pokemon_language = [config['pokemon-language']]
    pokemon_path_source = "locale/{0}/pkmn.json".format(config['pokemon-language'])

    # Load Pokemon list and raid info
    with open(os.path.join(script_path, pokemon_path_source), "r") as fd:
        pkmn_info = json.load(fd)
    with open(os.path.join(script_path, "raid_info.json"), "r") as fd:
        raid_info = json.load(fd)

    # Load type information
    with open(os.path.join(script_path, "type_chart.json"), "r") as fd:
        type_chart = json.load(fd)
    with open(os.path.join(script_path, "type_list.json"), "r") as fd:
        type_list = json.load(fd)

    # Set spelling dictionary to our list of Pokemon
    spelling.set_dictionary(pkmn_info['pokemon_list'])

load_config()

Clembot.config = config

"""

======================

Helper functions

======================

"""
# Given a Pokemon name, return a list of its
# weaknesses as defined in the type chart
def get_type(server, pkmn_number):
    pkmn_number = int(pkmn_number)-1
    types = type_list[pkmn_number]
    ret = []
    for type in types:
        ret.append(parse_emoji(server, config['type_id_dict'][type.lower()]))
    return ret

def get_name(pkmn_number):
    pkmn_number = int(pkmn_number)-1
    name = pkmn_info['pokemon_list'][pkmn_number].capitalize()
    return name

def get_number(pkm_name):
    number = pkmn_info['pokemon_list'].index(pkm_name) + 1
    return number

# Given a Pokemon name, return a list of its
# weaknesses as defined in the type chart
def get_weaknesses(species):
    # Get the Pokemon's number
    number = pkmn_info['pokemon_list'].index(species)
    # Look up its type
    pk_type = type_list[number]

    # Calculate sum of its weaknesses
    # and resistances.
    # -2 == immune
    # -1 == NVE
    #  0 == neutral
    #  1 == SE
    #  2 == double SE
    type_eff = {}
    for type in pk_type:
        for atk_type in type_chart[type]:
            if atk_type not in type_eff:
                type_eff[atk_type] = 0
            type_eff[atk_type] += type_chart[type][atk_type]

    # Summarize into a list of weaknesses,
    # sorting double weaknesses to the front and marking them with 'x2'.
    ret = []
    for type, effectiveness in sorted(type_eff.items(), key=lambda x: x[1], reverse=True):
        if effectiveness == 1:
            ret.append(type.lower())
        elif effectiveness == 2:
            ret.append(type.lower() + "x2")

    return ret


# Given a list of weaknesses, return a
# space-separated string of their type IDs,
# as defined in the type_id_dict
def weakness_to_str(server, weak_list):
    ret = ""
    for weakness in weak_list:
        # Handle an "x2" postfix defining a double weakness
        x2 = ""
        if weakness[-2:] == "x2":
            weakness = weakness[:-2]
            x2 = "x2"

        # Append to string
        ret += parse_emoji(server, config['type_id_dict'][weakness]) + x2 + " "

    return ret


# Convert an arbitrary string into something which
# is acceptable as a Discord channel name.
def sanitize_channel_name(name):
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub(r"[^a-zA-Z0-9 _\-]", "", name)
    # Replace spaces with dashes
    ret = ret.replace(" ", "-")
    return ret

# Given a string, if it fits the pattern :emoji name:,
# and <emoji_name> is in the server's emoji list, then
# return the string <:emoji name:emoji id>. Otherwise,
# just return the string unmodified.
def parse_emoji(server, emoji_string):
    if emoji_string[0] == ':' and emoji_string[-1] == ':':
        emoji = discord.utils.get(server.emojis, name=emoji_string.strip(':'))
        if emoji:
            emoji_string = "<:{0}:{1}>".format(emoji.name, emoji.id)
        else:
            emoji_string = "{0}".format(emoji_string.strip(':').capitalize())

    return emoji_string

def print_emoji_name(server, emoji_string):
    # By default, just print the emoji_string
    ret = "`" + emoji_string + "`"

    emoji = parse_emoji(server, emoji_string)
    # If the string was transformed by the parse_emoji
    # call, then it really was an emoji and we should
    # add the raw string so people know what to write.
    if emoji != emoji_string:
        ret = emoji + " (`" + emoji_string + "`)"

    return ret

# Given an arbitrary string, create a Google Maps
# query using the configured hints
def create_gmaps_query(details, channel):
    details_list = details.split()
    loc_list = server_dict[channel.server]['city_channels'][channel.name].split()
    return "https://www.google.com/maps/search/?api=1&query={0}+{1}".format('+'.join(details_list),'+'.join(loc_list))

# Given a User, check that it is Clembot's master
def check_master(user):
    return str(user) == config['master']

def check_server_owner(user, server):
    return str(user) == str(server.owner)

# Given a violating message, raise an exception
# reporting unauthorized use of admin commands
def raise_admin_violation(message):
    raise Exception(_("Received admin command {command} from unauthorized user, {user}!").format(command=message.content, user=message.author))

def spellcheck(word):
    suggestion = spelling.correction(word)

    # If we have a spellcheck suggestion
    if suggestion != word:
        return _("Beep Beep! \"{entered_word}\" is not a Pokemon! Did you mean \"{corrected_word}\"?").format(entered_word=word, corrected_word=spelling.correction(word))
    else:
        return _("Beep Beep! \"{entered_word}\" is not a Pokemon! Check your spelling!").format(entered_word=word)



async def expiry_check(channel):
    logger.info("Expiry_Check - "+channel.name)
    server = channel.server
    global active_raids
    if channel not in active_raids:
        active_raids.append(channel)
        logger.info("Expire_Channel - Channel Added To Watchlist - "+channel.name)
        while True:
            try:
                if server_dict[server]['raidchannel_dict'][channel]['active'] is True:
                    if server_dict[server]['raidchannel_dict'][channel]['exp'] is not None:
                        if server_dict[server]['raidchannel_dict'][channel]['exp'] <= time.time():
                            if server_dict[server]['raidchannel_dict'][channel]['type'] == 'egg':
                                pokemon = server_dict[server]['raidchannel_dict'][channel]['pokemon']
                                if pokemon != '':
                                    logger.info("Expire_Channel - Egg Auto Hatched - "+channel.name)
                                    try:
                                        active_raids.remove(channel)
                                    except ValueError:
                                        logger.info("Expire_Channel - Channel Removal From ActiveRaid Failed - Not in List - "+channel.name)
                                    await _eggtoraid(pokemon.lower(), channel)
                                    break
                            event_loop.create_task(expire_channel(channel))
                            try:
                                active_raids.remove(channel)
                            except ValueError:
                                logger.info("Expire_Channel - Channel Removal From ActiveRaid Failed - Not in List - "+channel.name)
                            logger.info("Expire_Channel - Channel Expired And Removed From Watchlist - "+channel.name)
                            break
            except KeyError:
                pass

            await asyncio.sleep(30)
            continue

async def expire_channel(channel):
    server = channel.server
    alreadyexpired = False
    logger.info("Expire_Channel - "+channel.name)
    # If the channel exists, get ready to delete it.
    # Otherwise, just clean up the dict since someone
    # else deleted the actual channel at some point.

    channel_exists = Clembot.get_channel(channel.id)
    if channel_exists is None:
        try:
            del server_dict[channel.server]['raidchannel_dict'][channel]
        except KeyError:
            pass
        return
    else:
        dupechannel = False
        if server_dict[server]['raidchannel_dict'][channel]['active'] == False:
            alreadyexpired = True
        else:
            server_dict[server]['raidchannel_dict'][channel]['active'] = False
        logger.info("Expire_Channel - Channel Expired - "+channel.name)
        try:
            testvar = server_dict[server]['raidchannel_dict'][channel]['duplicate']
        except KeyError:
            server_dict[server]['raidchannel_dict'][channel]['duplicate'] = 0
        if server_dict[server]['raidchannel_dict'][channel]['duplicate'] >= 3:
            dupechannel = True
            server_dict[server]['raidchannel_dict'][channel]['duplicate'] = 0
            server_dict[server]['raidchannel_dict'][channel]['exp'] = time.time()
            if not alreadyexpired:
                await Clembot.send_message(channel, _("""This channel has been successfully reported as a duplicate and will be deleted in 1 minute. Check the channel list for the other raid channel to coordinate in!
If this was in error, reset the raid with **!timerset**"""))
            delete_time = server_dict[server]['raidchannel_dict'][channel]['exp'] + (1 * 60) - time.time()
        elif server_dict[server]['raidchannel_dict'][channel]['type'] == 'egg':
            if not alreadyexpired:
                maybe_list = []
                trainer_dict = server_dict[channel.server]['raidchannel_dict'][channel]['trainer_dict']
                for trainer in trainer_dict.keys():
                    if trainer_dict[trainer]['status']=='maybe':
                        maybe_list.append(trainer)
                await Clembot.send_message(channel, _("""**This egg has hatched!**\n\n...or the time has just expired. Trainers {trainer_list}: Update the raid to the pokemon that hatched using **!raid <pokemon>** or reset the hatch timer with **!timerset**. This channel will be deactivated until I get an update and I'll delete it in 15 minutes if I don't hear anything.""").format(trainer_list=", ".join(maybe_list)))
            delete_time = server_dict[server]['raidchannel_dict'][channel]['exp'] + (15 * 60) - time.time()
        else:
            if not alreadyexpired:
                await Clembot.send_message(channel, _("""This channel timer has expired! The channel has been deactivated and will be deleted in 5 minutes.
To reactivate the channel, use !timerset to set the timer again."""))
            delete_time = server_dict[server]['raidchannel_dict'][channel]['exp'] + (5 * 60) - time.time()
        await asyncio.sleep(delete_time)
        # If the channel has already been deleted from the dict, someone
        # else got to it before us, so don't do anything.
        # Also, if the channel got reactivated, don't do anything either.

        try:
            if server_dict[channel.server]['raidchannel_dict'][channel]['active'] == False:
                if dupechannel:
                    reportmsg = server_dict[channel.server]['raidchannel_dict'][channel]['raidreport']
                    try:
                        await Clembot.delete_message(reportmsg)
                    except:
                        pass
                try:
                    del server_dict[channel.server]['raidchannel_dict'][channel]
                except KeyError:
                    pass
                    #channel doesn't exist anymore in serverdict
                channel_exists = Clembot.get_channel(channel.id)
                if channel_exists is None:
                    return
                else:
                    await Clembot.delete_channel(channel_exists)
                    logger.info("Expire_Channel - Channel Deleted - "+channel.name)
        except:
            pass


async def channel_cleanup(loop=True):
    while True:
        global active_raids
        serverdict_chtemp = copy.deepcopy(server_dict)
        logger.info("Channel_Cleanup ------ BEGIN ------")

        #for every server in save data
        for server in serverdict_chtemp.keys():

            log_str = "Channel_Cleanup - Server: "+server.name
            logger.info(log_str+" - BEGIN CHECKING SERVER")

            #clear channel lists
            dict_channel_delete = []
            discord_channel_delete =[]
            dict_expired_channel_list = []

            #check every raid channel data for each server
            for channel in serverdict_chtemp[server]['raidchannel_dict']:
                log_str = "Channel_Cleanup - Server: "+server.name
                log_str = log_str+": Channel:"+channel.name
                logger.info(log_str+" - CHECKING")

                channelmatch = Clembot.get_channel(channel.id)

                if channelmatch is None:
                    #list channel for deletion from save data
                    dict_channel_delete.append(channel)
                    logger.info(log_str+" - DOESN'T EXIST IN DISCORD")
                #otherwise, if Clembot can still see the channel in discord
                else:
                    logger.info(log_str+" - EXISTS IN DISCORD")
                    #if the channel save data shows it's not an active raid
                    if serverdict_chtemp[server]['raidchannel_dict'][channel]['active'] == False:

                        if serverdict_chtemp[server]['raidchannel_dict'][channel]['type'] == 'egg':

                            #and if it has been expired for longer than 5 minutes already
                            if serverdict_chtemp[server]['raidchannel_dict'][channel]['exp'] < (time.time() - (15 * 60)):

                                #list the channel to be removed from save data
                                dict_channel_delete.append(channel)

                                #and list the channel to be deleted in discord
                                discord_channel_delete.append(channel)

                                logger.info(log_str+" - 15+ MIN EXPIRY NONACTIVE EGG")
                                continue

                        else:

                            #and if it has been expired for longer than 5 minutes already
                            if serverdict_chtemp[server]['raidchannel_dict'][channel]['exp'] < (time.time() - (5 * 60)):

                                #list the channel to be removed from save data
                                dict_channel_delete.append(channel)

                                #and list the channel to be deleted in discord
                                discord_channel_delete.append(channel)

                                logger.info(log_str+" - 5+ MIN EXPIRY NONACTIVE RAID")
                                continue

                    #if the channel save data shows it as an active raid still
                    elif serverdict_chtemp[server]['raidchannel_dict'][channel]['active'] == True:

                        #if it's an exraid
                        if serverdict_chtemp[server]['raidchannel_dict'][channel]['type'] == 'exraid':

                            #check if it's expiry is not None
                            if serverdict_chtemp[server]['raidchannel_dict'][channel]['exp'] is not None:

                                #if so, set it to None (converting old exraid channels to new ones to prevent expiry)
                                try:
                                    server_dict[server]['raidchannel_dict'][channel]['exp'] = None
                                    logger.info(log_str+" - EXRAID - CONVERTED TO EXPIRY None")
                                except:
                                    pass

                            logger.info(log_str+" - EXRAID")
                            continue

                        #and if it has been expired for longer than 5 minutes already
                        elif serverdict_chtemp[server]['raidchannel_dict'][channel]['exp'] < (time.time() - (5 * 60)):

                            #list the channel to be removed from save data
                            dict_channel_delete.append(channel)

                            #and list the channel to be deleted in discord
                            discord_channel_delete.append(channel)

                            logger.info(log_str+" - 5+ MIN EXPIRY ACTIVE")
                            continue

                        #or if the expiry time for the channel has already passed within 5 minutes
                        elif serverdict_chtemp[server]['raidchannel_dict'][channel]['exp'] <= time.time():

                            #list the channel to be sent to the channel expiry function
                            dict_expired_channel_list.append(channel)

                            logger.info(log_str+" - RECENTLY EXPIRED")
                            continue

                        else:
                            #if channel is still active, make sure it's expiry is being monitored
                            if channel not in active_raids:
                                event_loop.create_task(expiry_check(channel))
                                logger.info(log_str+" - MISSING FROM EXPIRY CHECK")
                                continue

            #for every channel listed to have save data deleted
            for c in dict_channel_delete:
                try:
                    #attempt to delete the channel from save data
                    del server_dict[server]['raidchannel_dict'][c]
                    logger.info("Channel_Cleanup - Channel Savedata Cleared - " + c.name)
                except KeyError:
                    pass

                try:
                    #delete channel if it still exists in discord
                    Clembot.delete_channel(c)
                    logger.info("Channel_Cleanup - Channel Deleted - " + c.name)
                except:
                    logger.info("Channel_Cleanup - Channel Deletion Failure - " + c.name)
                    pass

            #for every channel listed to have the discord channel deleted
            for c in discord_channel_delete:
                try:
                    #delete channel from discord
                    await Clembot.delete_channel(c)
                    logger.info("Channel_Cleanup - Channel Deleted - " + c.name)
                except:
                    logger.info("Channel_Cleanup - Channel Deletion Failure - " + c.name)
                    pass

            #for every channel listed to have recently expired
            for e in dict_expired_channel_list:
                event_loop.create_task(expire_channel(e))

        #save server_dict changes after cleanup
        logger.info("Channel_Cleanup - SAVING CHANGES")
        await _save()
        logger.info("Channel_Cleanup ------ END ------")

        await asyncio.sleep(600)#600 default
        continue

async def server_cleanup(loop=True):
    while True:
        serverdict_srvtemp = copy.deepcopy(server_dict)
        logger.info("Server_Cleanup ------ BEGIN ------")

        serverdict_srvtemp = server_dict
        dict_server_list = []
        bot_server_list = []
        dict_server_delete = []

        for server in serverdict_srvtemp.keys():
            dict_server_list.append(server)
        for server in Clembot.servers:
            bot_server_list.append(server)
        server_diff = set(dict_server_list) - set(bot_server_list)
        for s in server_diff:
            dict_server_delete.append(s)

        for s in dict_server_delete:
            try:
                del server_dict[s]
                logger.info("Server_Cleanup - Cleared "+s.name+" from save data")
            except KeyError:
                pass

        logger.info("Server_Cleanup - SAVING CHANGES")
        await _save()
        logger.info("Server_Cleanup ------ END ------")
        await asyncio.sleep(1800)#1800 default
        continue

async def reboot_msg(owners,loop=False,):
    msg_success = 0
    msg_fail = 0
    reboot_msg = """**Beep Beep! That's right! I've been updated!**

**Changes:**
    - **!list** and status update bug should be fixed.
    - Old timer formats no longer break map links, and instead are accepted and parsed as valid times.
    - Command checks have been remodelled, resulting in **!help** showing only relevant commands based on context.
    - **!unwant all** has been added, so people can remove all their pokemon roles.
    - **!clearstatus** has been added for use in raid channels. This clears all status counts for that raid.
    - **!invite** now can be used seperately before uploading the image of your pass. Clembot will wait for 30 seconds after !invite is used.
    - General housekeeping and spelling corrections.

You may have experienced issues with **!list**
not working in certain raid channels and
report channels.

This was due to a bug that allowed incorrect
values for **!interested**, **!coming** and **!here**
status updates.

If you still have a raid channel that has
the **!list** command not working (such as an
EXRaid) you can resolve them by using
**!clearstatus**. This will clear all status
values, including the incorrect ones.

Only members who hold the **manage_server**
permission are able to use this new command.

**Reconfigure shouldn't be necessary for this update.**"""
    logger.info("Reboot Messages ------ BEGIN ------")
    for o in owners:
        try:
            await Clembot.send_message(o, reboot_msg)
            msg_success += 1
            logger.info("Reboot Message - SENT - "+o.name)
        except:
            msg_fail += 1
            logger.info("Reboot Message - FAILED - "+o.name)

        #step through slowly to prevent rate limits
        await asyncio.sleep(0.5)#0.5 default
        continue
    logger.info("Reboot Messages ------ END ------")
    print(_("\nReboot messages sent: {success_count} successful, {fail_count} failed.").format(success_count=msg_success,fail_count=msg_fail))
    return

async def maint_start():
    try:
        event_loop.create_task(server_cleanup())
        event_loop.create_task(channel_cleanup())
        logger.info("Maintenance Tasts Started")
    except KeyboardInterrupt as e:
        tasks.cancel()

event_loop = asyncio.get_event_loop()

"""

======================

End helper functions

======================

"""


"""
Clembot tracks raiding commands through the raidchannel_dict.
Each channel contains the following fields:
'trainer_dict' : a dictionary of all trainers interested in the raid.
'exp'          : an instance of time.struct_time tracking when the raid ends.
'active'       : a Boolean indicating whether the raid is still active.

The trainer_dict contains "trainer" elements, which have the following fields:
'status' : a string indicating either "omw" or "waiting"
'count'  : the number of trainers in the party
"""

team_msg = " or ".join(["'!team {0}'".format(team) for team in config['team_dict'].keys()])


@Clembot.event
async def on_ready():
    print(_("Starting up...")) #prints to the terminal or cmd prompt window upon successful connection to Discord
    REBOOT = False
    if 'reboot' in sys.argv[1:]:
        REBOOT = True
    owners = []
    msg_success = 0
    msg_fail = 0
    servers = len(Clembot.servers)
    users = 0
    for server in Clembot.servers:
        users += len(server.members)
        try:
            if server not in server_dict:
                server_dict[server] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}}
        except KeyError:
            server_dict[server] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}}

        owners.append(server.owner)

    print(_("Beep Beep! That's right!\n\n{server_count} servers connected.\n{member_count} members found.").format(server_count=servers,member_count=users))

    if REBOOT:
        event_loop.create_task(reboot_msg(owners))

    await maint_start()



@Clembot.event
async def on_server_join(server):
    owner = server.owner
    server_dict[server] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}}
    await Clembot.send_message(owner, _("Beep Beep! I'm Clembot, a Discord helper bot for Pokemon Go communities, and someone has invited me to your server! Type **!help** to see a list of things I can do, and type **!configure** in any channel of your server to begin!"))

@Clembot.event
async def on_server_remove(server):
    try:
        if server in server_dict[server]:
            try:
                del server_dict[server]
            except KeyError:
                pass
    except KeyError:
        pass

@Clembot.command(pass_context=True, hidden=True)
@commands.has_permissions(manage_server=True)
async def configure(ctx):
    server = ctx.message.server
    owner = ctx.message.author
    server_dict_temp = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'welcomechan': "", 'wantset': False, 'raidset': False, 'wildset': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}}
    await Clembot.send_message(owner, _("""__**Clembot Configuration**__\nBeep Beep! That's Right! Welcome to the configuration for Clembot the Pokemon Go Helper Bot! I will be guiding you through some setup steps to get me setup on your server.\n\n**Role Setup**\nBefore you begin the configuration, please make sure my role is moved to the top end of the server role hierarchy. It can be under admins and mods, but must be above team ands general roles. Here is an example: <http://i.imgur.com/c5eaX1u.png>\n\nReply with **cancel** at any time throughout the questions to cancel the configure process.\n\n**Team Assignments**\nTeam assignment allows users to assign their Pokemon Go team role using the **!team** command. If you have a bot that handles this already, you may want to disable this feature.\nIf you are to use this feature, ensure existing team roles are as follows: mystic, valor, instinct. These must be all lowercase letters. If they don't exist yet, I'll make some for you instead.\n\nRespond with: **N** to disable, **Y** to enable:"""))
    while True:
        teamreply = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
        if teamreply.content.lower() == "y":
            server_dict_temp['team']=True
            for team in config['team_dict'].keys():
                temp_role = discord.utils.get(server.roles, name=team)
                if temp_role == None:
                    await Clembot.create_role(server = server, name = team, hoist = False, mentionable = True)
            await Clembot.send_message(owner, _("**Team Assignments enabled!**\n---"))
            break
        elif teamreply.content.lower() == "n":
            server_dict_temp['team']=False
            await Clembot.send_message(owner, _("**Team Assignments disabled!**\n---"))
            break
        elif teamreply.content.lower() == "cancel":
            await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
            return
        else:
            await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
            continue

    await Clembot.send_message(owner, _("**Welcome Message**\n\n I can welcome new members to the server with a short message. Here is an example:\n"))
    if server_dict_temp['team'] == True:
        await Clembot.send_message(owner, _("Beep Beep! Welcome to {server_name}, {owner_name.mention}! Set your team by typing '**!team mystic**' or '**!team valor**' or '**!team instinct**' without quotations. If you have any questions just ask an admin.").format(server_name=server.name, owner_name=owner))
    else:
        await Clembot.send_message(owner, _("Beep Beep! Welcome to {server_name}, {owner_name.mention}! If you have any questions just ask an admin.").format(server_name=server, owner_name=owner))
    await Clembot.send_message(owner, _("This welcome message can be in a specific channel or a direct message. If you have a bot that handles this already, you may want to disable this feature.\n\nRespond with: **N** to disable, **Y** to enable:"))
    while True:
        welcomereply = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
        if welcomereply.content.lower() == "y":
            server_dict_temp['welcome'] = True
            await Clembot.send_message(owner, _("**Welcome Message enabled!**\n---\n**Welcome Message Channels**\nWhich channel in your server would you like me to post the Welcome Messages? You can also choose to have them sent to the new member via Direct Message (DM) instead.\n\nRespond with: **channel-name** of a channel in your server or **DM** to Direct Message:"))
            wchcheck = 0
            while True:
                welcomechannelreply = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
                if welcomechannelreply.content.lower() == "dm":
                    server_dict_temp['welcomechan'] = "dm"
                    break
                elif " " in welcomechannelreply.content.lower():
                    await Clembot.send_message(owner, _("Channel names can't contain spaces, sorry. Please double check the name and send your response again."))
                    continue
                elif welcomechannelreply.content.lower() == "cancel":
                    await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                    return
                else:
                    server_channel_list = []
                    for channel in server.channels:
                        server_channel_list.append(channel.name)
                    diff = set([welcomechannelreply.content.lower().strip()]) - set(server_channel_list)
                    if not diff:
                        server_dict_temp['welcomechan'] = welcomechannelreply.content.lower()
                        await Clembot.send_message(owner, _("**Welcome Channel set**\n---"))
                        break
                    else:
                        await Clembot.send_message(owner, _("The channel you provided isn't in your server. Please double check your channel name and resend your response."))
                        continue
        elif welcomereply.content.lower() == "n":
            server_dict_temp['welcome'] = False
            await Clembot.send_message(owner, _("**Welcome Message disabled!**\n---"))
            break
        elif welcomereply.content.lower() == "cancel":
            await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
            return
        else:
            await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
            continue
        break
    await Clembot.send_message(owner, _("**Main Functions**\nMain Functions include:\n - **!want** and creating tracked Pokemon roles \n - **!wild** Pokemon reports\n - **!raid** reports and channel creation for raid management.\nIf you don't want __any__ of the Pokemon tracking or Raid management features, you may want to disable them.\n\nRespond with: **N** to disable, or **Y** to enable:"))
    while True:
        otherreply = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
        if otherreply.content.lower() == "y":
            server_dict_temp['other']=True
            await Clembot.send_message(owner, _("**Main Functions enabled**\n---\n**Reporting Channels**\nPokemon raid or wild reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`"))

            await Clembot.send_message(owner, _("If you do not require raid and wild reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:"))
            citychannel_dict = {}
            while True:
                citychannels = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
                if citychannels.content.lower() == "n":
                    server_dict_temp['wildset']=False
                    server_dict_temp['raidset']=False
                    await Clembot.send_message(owner, _("**Reporting Channels disabled**\n---"))
                    break
                elif citychannels.content.lower() == "cancel":
                    await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                    return
                else:
                    citychannel_list = citychannels.content.lower().split(', ')
                    server_channel_list = []
                    for channel in server.channels:
                        server_channel_list.append(channel.name)

                    diff = set(citychannel_list) - set(server_channel_list)
                    if not diff:
                        await Clembot.send_message(owner, _("**Reporting Channels enabled**\n---"))
                    else:
                        await Clembot.send_message(owner, _("The channel list you provided doesn't match with your servers channels.\nThe following aren't in your server: {invalid_channels}\nPlease double check your channel list and resend your reponse.").format(invalid_channels=", ".join(diff)))
                        continue

                await Clembot.send_message(owner, _("""**Report Locations**\nFor each report, I generate Google Maps links to give people directions to raids and spawns! To do this, I need to know which suburb/town/region each report channel represents, to ensure we get the right location in the map. For each report channel you provided, I will need it's corresponding general location using only letters and spaces, with each location seperated by a comma and space.\nExample: `kansas city mo, hull uk, sydney nsw australia`\nEach location will have to be in the same order as you provided the channels in the previous question.\n\nRespond with: **location info, location info, location info** each matching the order of the previous channel list:"""))
                while True:
                    cities = await Clembot.wait_for_message(author=owner, check=lambda message: message.server is None)
                    if cities.content.lower() == "cancel":
                        await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                        return
                    city_list = cities.content.split(', ')
                    if len(city_list) == len(citychannel_list):
                        for i in range(len(citychannel_list)):
                            citychannel_dict[citychannel_list[i]]=city_list[i]
                        break
                    else:
                        await Clembot.send_message(owner, _("""The number of cities don't match the number of channels you gave me earlier!\nI'll show you the two lists to compare:\n{channellist}\n{citylist}\nPlease double check that your locations match up with your provided channels and resend your response.""").format(channellist=(", ".join(citychannel_list)), citylist=(", ".join(city_list))))
                        continue
                server_dict_temp['city_channels'] = citychannel_dict
                await Clembot.send_message(owner, _("**Report Locations are set**\n---\n**Raid Reports**\nDo you want **!raid** reports enabled? If you want __only__ the **!wild** feature for reports, you may want to disable this.\n\nRespond with: **N** to disable, or **Y** to enable:"))
                while True:
                    raidconfigset = await Clembot.wait_for_message(author=owner, check=lambda message: message.server is None)
                    if raidconfigset.content.lower() == "y":
                        server_dict_temp['raidset']=True
                        await Clembot.send_message(owner, _("**Raid Reports enabled**\n---"))
                        break
                    elif raidconfigset.content.lower() == "n":
                        server_dict_temp['raidset']=False
                        await Clembot.send_message(owner, _("**Raid Reports disabled**\n---"))
                        break
                    elif raidconfigset.content.lower() == "cancel":
                        await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                        return
                    else:
                        await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                        continue
                await Clembot.send_message(owner, _("**Wild Reports**\nDo you want **!wild** reports enabled? If you want __only__ the **!raid** feature for reports, you may want to disable this.\n\nRespond with: **N** to disable, or **Y** to enable:"))
                while True:
                    wildconfigset = await Clembot.wait_for_message(author=owner, check=lambda message: message.server is None)
                    if wildconfigset.content.lower() == "y":
                        server_dict_temp['wildset']=True
                        await Clembot.send_message(owner, _("**Wild Reports enabled**\n---"))
                        break
                    elif wildconfigset.content.lower() == "n":
                        server_dict_temp['wildset']=False
                        await Clembot.send_message(owner, _("**Wild Reports disabled**\n---"))
                        break
                    elif wildconfigset.content.lower() == "cancel":
                        await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                        return
                    else:
                        await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                        continue
                break
            await Clembot.send_message(owner, _("""**Pokemon Notifications**\nThe **!want** and **!unwant** commands let you add or remove roles for Pokemon that will be mentioned in reports. This let you get notifications on the Pokemon you want to track. I just need to know what channels you want to allow people to manage their pokemon with the **!want** and **!unwant** command. If you pick a channel that doesn't exist, I'll make it for you.\nIf you don't want to allow the management of tracked Pokemon roles, then you may want to disable this feature.\n\nRepond with: **N** to disable, or the **channel-name** list to enable, each seperated by a comma and space."""))
            while True:
                wantchs = await Clembot.wait_for_message(author=owner, check=lambda message: message.server is None)
                if wantchs.content.lower() == "n":
                    server_dict_temp['wantset']=False
                    await Clembot.send_message(owner, _("**Pokemon Notifications disabled**\n---"))
                    break
                else:
                    want_list = wantchs.content.lower().split(', ')
                    server_channel_list = []
                    for channel in server.channels:
                        server_channel_list.append(channel.name)
                    diff = set(citychannel_list) - set(server_channel_list)
                    if not diff:
                        server_dict_temp['wantset']=True
                        await Clembot.send_message(owner, _("**Pokemon Notifications enabled**\n---"))
                        while True:
                            try:
                                for want_channel_name in want_list:
                                    want_channel = discord.utils.get(server.channels, name = want_channel_name)
                                    if want_channel == None:
                                        want_channel = await Clembot.create_channel(server, want_channel_name)
                                    if want_channel not in server_dict_temp['want_channel_list']:
                                        server_dict_temp['want_channel_list'].append(want_channel)
                                break
                            except:
                                await Clembot.send_message(owner, _("Beep Beep! You didn't give me enough permissions to create channels! Please check my permissions and that my role is above general roles. Let me know if you'd like me to check again.\n\nRespond with: **Y** to try again, or **N** to skip and create the missing channels yourself."))
                                while True:
                                    wantpermswait = await Clembot.wait_for_message(author=owner, check=lambda message: message.server is None)
                                    if wantpermswait.content.lower() == "n":
                                        break
                                    elif wantpermswait.content.lower() == "y":
                                        break
                                    elif wantpermswait.content.lower() == "cancel":
                                        await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                                        return
                                    else:
                                        await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **Y** to try again, or **N** to skip and create the missing channels yourself."))
                                        continue
                                if wantpermswait.content.lower() == "y":
                                    continue
                                break
                    else:
                        await Clembot.send_message(owner, _("The channel list you provided doesn't match with your servers channels.\nThe following aren't in your server:{invalid_channels}\nPlease double check your channel list and resend your reponse.").format(invalid_channels=", ".join(diff)))
                        continue
                    break
            if server_dict_temp['raidset'] == True:
                await Clembot.send_message(owner, _("**Timezone Configuration**\nTo help coordinate raids reports for you, I need to know what timezone you're in! The current 24-hr time UTC is {utctime}. How many hours off from that are you?\n\nRespond with: A number from **-12** to **12**:").format(utctime=strftime("%H:%M", time.gmtime())))
                while True:
                    offsetmsg = await Clembot.wait_for_message(author = owner, check=lambda message: message.server is None)
                    if offsetmsg.content.lower() == "cancel":
                        await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
                        return
                    else:
                        try:
                            offset = float(offsetmsg.content)
                        except ValueError:
                            await Clembot.send_message(owner, _("I couldn't convert your answer to an appropriate timezone!.\nPlease double check what you sent me and resend a number strarting from **-12** to **12**."))
                            continue
                        if not -12 <= offset <= 14:
                            await Clembot.send_message(owner, _("I couldn't convert your answer to an appropriate timezone!.\nPlease double check what you sent me and resend a number strarting from **-12** to **12**."))
                            continue
                        else:
                            break
                server_dict_temp['offset'] = offset
                await Clembot.send_message(owner, _("**Timezone set**\n---"))
                break
            else:
                break
        elif otherreply.content.lower() == "n":
            server_dict_temp['other']=False
            server_dict_temp['raidset']=False
            server_dict_temp['wildset']=False
            server_dict_temp['wantset']=False
            server_dict_temp['done']=True
            await Clembot.send_message(owner, _("**Main Functions disabled**\n---"))
            break
        elif otherreply.content.lower() == "cancel":
            await Clembot.send_message(owner, _("**CONFIG CANCELLED!**\nNo changes have been made."))
            return
        else:
            await Clembot.send_message(owner, _("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
            continue

    server_dict_temp['done']=True
    server_dict[server] = server_dict_temp
    await Clembot.send_message(owner, _("Beep Beep! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again."))

"""Welcome message to the server and some basic instructions."""

@Clembot.event
async def on_member_join(member):
    server = member.server
    if server_dict[server]['done'] == False or server_dict[server]['welcome'] == False:
        return

    # Build welcome message

    admin_message = _(" If you have any questions just ask an admin.")

    welcomemessage = _("Beep Beep! Welcome to {server_name}, {new_member_name}! ")
    if server_dict[server]['team'] == True:
        welcomemessage += _("Set your team by typing {team_command} without quotations.").format(team_command=team_msg)
    welcomemessage += admin_message

    if server_dict[server]['welcomechan'] == "dm":
        await Clembot.send_message(member, welcomemessage.format(server_name=server.name, new_member_name=member.mention))

    else:
        default = discord.utils.get(server.channels, name = server_dict[server]['welcomechan'])
        if not default:
            print(_("WARNING: no default channel configured. Unable to send welcome message."))
        await Clembot.send_message(default, welcomemessage.format(server_name=server.name, new_member_name=member.mention))


"""

Admin commands

"""

async def _save():
    with tempfile.NamedTemporaryFile(
        'wb', dir=os.path.dirname('serverdict'), delete=False) as tf:
        pickle.dump(server_dict, tf)
        tempname = tf.name
    try:
        os.remove('serverdict_backup')
    except OSError as e:
        pass
    try:
        os.rename('serverdict', 'serverdict_backup')
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

    os.rename(tempname, 'serverdict')

@Clembot.command(pass_context=True)
@checks.is_owner()
async def exit(ctx):
    """Exit after saving.

    Usage: !exit.
    Calls the save function and quits the script."""
    try:
        await _save()
    except Exception as err:
        print(_("Error occured while trying to save!"))
        print(err)
    quit()

@Clembot.command(pass_context=True)
@checks.is_owner()
async def save(ctx):
    """Save persistent state to file.

    Usage: !save
    File path is relative to current directory."""
    try:
        await _save()
        logger.info("CONFIG SAVED")
    except Exception as err:
        print(_("Error occured while trying to save!"))
        print(err)

@Clembot.command(pass_context=True, hidden=True)
@commands.has_permissions(manage_server=True)
async def outputlog(ctx):
    """Get current Clembot log.

    Usage: !outputlog
    Output is a link to hastebin."""
    with open('logs\meowth.log', 'r') as logfile:
        logdata=logfile.read()
    logdata = logdata.encode('ascii', errors='replace').decode('utf-8')
    await Clembot.send_message(ctx.message.channel, hastebin.post(logdata))


"""

End admin commands

"""

@Clembot.command(pass_context = True)
@checks.teamset()
@checks.notraidchannel()
async def team(ctx):
    """Set your team role.

    Usage: !team <team name>
    The team roles have to be created manually beforehand by the server administrator."""

    server = ctx.message.server
    toprole = server.me.top_role.name
    position = server.me.top_role.position
    high_roles = []

    for team in config['team_dict'].keys():
        temp_role = discord.utils.get(ctx.message.server.roles, name=team)
        if temp_role.position > position:
            high_roles.append(temp_role.name)

    if high_roles:
        await Clembot.send_message(ctx.message.channel, _("Beep Beep! My roles are ranked lower than the following team roles: **{higher_roles_list}**\nPlease get an admin to move my roles above them!").format(higher_roles_list=', '.join(high_roles)))
        return

    role = None
    entered_team = ctx.message.content[6:].lower()
    role = discord.utils.get(ctx.message.server.roles, name=entered_team)

    # Check if user already belongs to a team role by
    # getting the role objects of all teams in team_dict and
    # checking if the message author has any of them.
    for team in config['team_dict'].keys():
        temp_role = discord.utils.get(ctx.message.server.roles, name=team)
        # If the role is valid,
        if temp_role:
            # and the user has this role,
            if temp_role in ctx.message.author.roles:
                # then report that a role is already assigned
                await Clembot.send_message(ctx.message.channel, _("Beep Beep! You already have a team role!"))
                return
        # If the role isn't valid, something is misconfigured, so fire a warning.
        else:
            print(_("WARNING: Role {team_role} in team_dict not configured as a role on the server!").format(team_role=team))
    # Check if team is one of the three defined in the team_dict

    if entered_team not in config['team_dict'].keys():
        await Clembot.send_message(ctx.message.channel, _("Beep Beep! \"{entered_team}\" isn't a valid team! Try {available_teams}").format(entered_team=entered_team, available_teams=team_msg))
        return
    # Check if the role is configured on the server
    elif role is None:
        await Clembot.send_message(ctx.message.channel, _("Beep Beep! The \"{entered_team}\" role isn't configured on this server! Contact an admin!").format(entered_team=entered_team))
    else:
        try:
            await Clembot.add_roles(ctx.message.author, role)
            await Clembot.send_message(ctx.message.channel, _("Beep Beep! Added {member} to Team {team_name}! {team_emoji}").format(member=ctx.message.author.mention, team_name=role.name.capitalize(), team_emoji=config['team_dict'][entered_team]))
        except discord.Forbidden:
            await Clembot.send_message(ctx.message.channel, _("Beep Beep! I can't add roles!"))

@Clembot.command(pass_context = True)
@checks.wantset()
@checks.notraidchannel()
async def want(ctx):
    """Add a Pokemon to your wanted list.

    Usage: !want <species>
    Clembot will mention you if anyone reports seeing
    this species in their !wild or !raid command."""

    """Behind the scenes, Clembot tracks user !wants by
    creating a server role for the Pokemon species, and
    assigning it to the user."""
    message = ctx.message
    server = message.server
    channel = message.channel
    if checks.check_wantchannel(ctx):
        entered_want = message.content[6:].lower()
        if entered_want not in pkmn_info['pokemon_list']:
            await Clembot.send_message(channel, spellcheck(entered_want))
            return
        role = discord.utils.get(server.roles, name=entered_want)
        # Create role if it doesn't exist yet
        if role is None:
            role = await Clembot.create_role(server = server, name = entered_want, hoist = False, mentionable = True)
            await asyncio.sleep(0.5)

        # If user is already wanting the Pokemon,
        # print a less noisy message
        if role in ctx.message.author.roles:
            await Clembot.send_message(channel, content=_("Beep Beep! {member}, I already know you want {pokemon}!").format(member=ctx.message.author.mention, pokemon=entered_want.capitalize()))
        else:
            await Clembot.add_roles(ctx.message.author, role)
            want_number = pkmn_info['pokemon_list'].index(entered_want) + 1
            want_img_url = "http://floatzel.net/pokemon/black-white/sprites/images/{0}.png".format(str(want_number)) #This part embeds the sprite
            want_embed = discord.Embed(colour=discord.Colour(0x2ecc71))
            want_embed.set_thumbnail(url=want_img_url)
            await Clembot.send_message(channel, content=_("Beep Beep! Got it! {member} wants {pokemon}").format(member=ctx.message.author.mention, pokemon=entered_want.capitalize()), embed=want_embed)
    else:
        want_channels = server_dict[server]['want_channel_list']
        await ctx.bot.send_message(channel, "Beep Beep! Please use one of the following channels for **!want** commands: {want_channel_list}".format(want_channel_list=", ".join(c.mention for c in want_channels)))

@Clembot.group(pass_context=True)
@checks.wantset()
@checks.notraidchannel()
async def unwant(ctx):
    """Remove a Pokemon from your wanted list.

    Usage: !unwant <species>
    You will no longer be notified of reports about this Pokemon."""

    """Behind the scenes, Clembot removes the user from
    the server role for the Pokemon species."""
    message = ctx.message
    server = message.server
    channel = message.channel
    if ctx.invoked_subcommand is None:
        if checks.check_wantchannel(ctx):
            entered_unwant = ctx.message.content[8:].lower()
            role = discord.utils.get(ctx.message.server.roles, name=entered_unwant)
            if entered_unwant not in pkmn_info['pokemon_list']:
                await Clembot.send_message(ctx.message.channel, spellcheck(entered_unwant))
                return
            else:
                # If user is not already wanting the Pokemon,
                # print a less noisy message
                if role not in ctx.message.author.roles:
                    await Clembot.add_reaction(ctx.message, '✅')
                else:
                    await Clembot.remove_roles(ctx.message.author, role)
                    unwant_number = pkmn_info['pokemon_list'].index(entered_unwant) + 1
                    await Clembot.add_reaction(ctx.message, '✅')

        else:
            want_channels = server_dict[server]['want_channel_list']
            await ctx.bot.send_message(channel, "Beep Beep! Please use one of the following channels for **!unwant** commands: {want_channel_list}".format(want_channel_list=", ".join(c.mention for c in want_channels)))

@unwant.command(pass_context=True)
@checks.wantset()
@checks.notraidchannel()
async def all(ctx):
    """Remove all Pokemon from your wanted list.

    Usage: !unwant all
    All Pokemon roles are removed."""

    """Behind the scenes, Clembot removes the user from
    the server role for the Pokemon species."""
    message = ctx.message
    server = message.server
    channel = message.channel
    author = message.author
    if checks.check_wantchannel(ctx):
        await Clembot.send_typing(ctx.message.channel)
        count = 0
        roles = author.roles
        remove_roles = []
        for role in roles:
            if role.name in pkmn_info['pokemon_list']:
                remove_roles.append(role)
                count += 1
            continue
        await Clembot.remove_roles(author, *remove_roles)
        if count == 0:
            await Clembot.send_message(ctx.message.channel, content=_("{0}, you have no pokemon in your want list.").format(ctx.message.author.mention, count))
        await Clembot.send_message(ctx.message.channel, content=_("{0}, I've removed {1} pokemon from your want list.").format(ctx.message.author.mention, count))
        return

    else:
        want_channels = server_dict[server]['want_channel_list']
        await ctx.bot.send_message(channel, "Beep Beep! Please use one of the following channels for **!unwant** commands: {want_channel_list}".format(want_channel_list=", ".join(c.mention for c in want_channels)))


@Clembot.command(pass_context = True)
@checks.citychannel()
@checks.wildset()
async def wild(ctx):
    """Report a wild Pokemon spawn location.

    Usage: !wild <species> <location>
    Clembot will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in."""
    await _wild(ctx.message)


async def _wild(message):
    space1 = message.content.find(" ",6)
    if space1 == -1:
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!wild <pokemon name> <location>**"))
        return
    else:
        content = message.content[6:].lower()
        entered_wild = content.split(' ',1)[0]
        wild_details = content.split(' ',1)[1]
        if entered_wild not in pkmn_info['pokemon_list']:
            entered_wild2 = ' '.join([content.split(' ',2)[0],content.split(' ',2)[1]])
            if entered_wild2 in pkmn_info['pokemon_list']:
                entered_wild = entered_wild2
                try:
                    wild_details = content.split(' ',2)[2]
                except IndexError:
                    await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!wild <pokemon name> <location>**"))
                    return
        wild_gmaps_link = create_gmaps_query(wild_details, message.channel)


    if entered_wild not in pkmn_info['pokemon_list']:
        await Clembot.send_message(message.channel, spellcheck(entered_wild))
        return
    else:
        wild = discord.utils.get(message.server.roles, name = entered_wild)
        if wild is None:
            wild = await Clembot.create_role(server = message.server, name = entered_wild, hoist = False, mentionable = True)
            await asyncio.sleep(0.5)
        wild_number = pkmn_info['pokemon_list'].index(entered_wild) + 1
        wild_img_url = "http://floatzel.net/pokemon/black-white/sprites/images/{0}.png".format(str(wild_number))
        wild_embed = discord.Embed(title=_("Beep Beep! Click here for directions to the wild {pokemon}!").format(pokemon=entered_wild.capitalize()),url=wild_gmaps_link,description=_("This is just my best guess!"),colour=discord.Colour(0x2ecc71))
        wild_embed.set_thumbnail(url=wild_img_url)
        await Clembot.send_message(message.channel, content=_("Beep Beep! Wild {pokemon} reported by {member}! Details: {location_details}").format(pokemon=wild.mention, member=message.author.mention, location_details=wild_details), embed=wild_embed)

@Clembot.command(pass_context=True)
@checks.cityeggchannel()
@checks.raidset()
async def raid(ctx):
    """Report an ongoing raid.

    Usage: !raid <species> <location>
    Clembot will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in.
    Clembot's message will also include the type weaknesses of the boss.

    Finally, Clembot will create a separate channel for the raid report, for the purposes of organizing the raid."""
    await _raid(ctx.message)

async def _raid(message):
    fromegg = False
    if message.channel.name not in server_dict[message.server]['city_channels'].keys():
        if message.channel in server_dict[message.channel.server]['raidchannel_dict'] and server_dict[message.channel.server]['raidchannel_dict'][message.channel]['type'] == 'egg':
            fromegg = True
        else:
            await Clembot.send_message(message.channel, _("Beep Beep! Please restrict raid reports to a city channel!"))
            return
    args = message.clean_content[5:]

    args_split = args.split(" ")
    del args_split[0]
    if fromegg is True:
        if args_split[0] == 'assume':
            if server_dict[message.channel.server]['raidchannel_dict'][message.channel]['active'] == False:
                await _eggtoraid(args_split[1].lower(), message.channel)
                return
            else:
                await _eggassume(" ".join(args_split), message.channel)
                return
        else:
            if server_dict[message.channel.server]['raidchannel_dict'][message.channel]['active'] == False:
                await _eggtoraid(" ".join(args_split).lower(), message.channel)
                return
            else:
                await Clembot.send_message(message.channel, _("Beep Beep! Please wait until the egg has hatched before changing it to an open raid!"))
                return
    elif len(args_split) <= 1:
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!raid <pokemon name> <location>**"))
        return
    entered_raid = re.sub("[\@]", "", args_split[0].lower())
    del args_split[0]

    if args_split[-1].isdigit():
        raidexp = args_split[-1]
        del args_split[-1]
    elif ":" in args_split[-1]:
        args_split[-1] = re.sub(r"[a-zA-Z]", "", args_split[-1])
        if args_split[-1].split(":")[0] == "":
            endhours = 0
        else:
            endhours = int(args_split[-1].split(":")[0])
        if args_split[-1].split(":")[1] == "":
            endmins = 0
        else:
            endmins = int(args_split[-1].split(":")[1])
        raidexp = 60 * endhours + endmins
        del args_split[-1]
    else:
        raidexp = False

    if entered_raid not in pkmn_info['pokemon_list']:
        await Clembot.send_message(message.channel, spellcheck(entered_raid))
        return
    if entered_raid not in pkmn_info['raid_list'] and entered_raid in pkmn_info['pokemon_list']:
        await Clembot.send_message(message.channel, _("Beep Beep! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
        return

    raid_details = " ".join(args_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!raid <pokemon name> <location>**"))
        return
    raid_gmaps_link = create_gmaps_query(raid_details, message.channel)

    raid_channel_name = entered_raid + "-" + sanitize_channel_name(raid_details)
    raid_channel = await Clembot.create_channel(message.server, raid_channel_name, *message.channel.overwrites)
    raid = discord.utils.get(message.server.roles, name = entered_raid)
    if raid is None:
        raid = await Clembot.create_role(server = message.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "http://floatzel.net/pokemon/black-white/sprites/images/{0}.png".format(str(raid_number))
    raid_embed = discord.Embed(title=_("Beep Beep! Click here for directions to the raid!"),url=raid_gmaps_link,description=_("Weaknesses: {weakness_list}").format(weakness_list=weakness_to_str(message.server, get_weaknesses(entered_raid))),colour=discord.Colour(0x2ecc71))
    raid_embed.set_thumbnail(url=raid_img_url)
    raidreport = await Clembot.send_message(message.channel, content = _("Beep Beep! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
    await asyncio.sleep(1) #Wait for the channel to be created.

    raidmsg = _("""Beep Beep! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!
This channel will be deleted five minutes after the timer expires.
** **
Please type `!beep` if you need a refresher of Clembot commands! 
""").format(
        pokemon=raid.mention, member=message.author.mention, citychannel=message.channel.mention,
        location_details=raid_details)

#     raidmsg = _("""Beep Beep! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!
#
# To update your status, choose from the following commands:
# **!interested, !coming, !here, !cancel**
# If you are bringing more than one trainer/account, add the number of accounts total on your first status update.
# Example: `!coming 5`
#
# To see the list of trainers who have given their status:
# **!list interested, !list coming, !list here**
# Alternatively **!list** by itself will show all of the above.
#
# **!location** will show the current raid location.
# **!location new <address>** will let you correct the raid address.
# Sending a Google Maps link will also update the raid location.
#
# **!timer** will show the current raid time.
# **!timerset** will let you correct the raid countdown time.
#
# Message **!starting** when the raid is beginning to clear the raid's 'here' list.
#
# This channel will be deleted five minutes after the timer expires.""").format(pokemon=raid.mention,
#                                                                               member=message.author.mention,
#                                                                               citychannel=message.channel.mention,
#                                                                               location_details=raid_details)
    raidmessage = await Clembot.send_message(raid_channel, content=raidmsg, embed=raid_embed)

    server_dict[message.server]['raidchannel_dict'][raid_channel] = {
        'reportcity' : message.channel.name,
        'trainer_dict' : {},
        'exp' : time.time() + 60 * 60, # One hour from now
        'manual_timer' : False, # No one has explicitly set the timer, Clembot is just assuming 2 hours
        'active' : True,
        'raidmessage' : raidmessage,
        'raidreport' : raidreport,
        'address' : raid_details,
        'type' : 'raid',
        'pokemon' : entered_raid,
        'egglevel' : '0',
        'suggested_start' : False
        }

    if raidexp:
        await _timerset(raid_channel,raidexp)
    else:
        await Clembot.send_message(raid_channel, content = _("Beep Beep! Hey {member}, if you can, set the time left on the raid using **!timerset <minutes>** so others can check it with **!timer**.").format(member=message.author.mention))

    event_loop.create_task(expiry_check(raid_channel))

# Print raid timer
async def print_raid_timer(channel):
    localexpiresecs = server_dict[channel.server]['raidchannel_dict'][channel]['exp'] + 3600 * server_dict[channel.server]['offset']
    localexpire = time.gmtime(localexpiresecs)
    timerstr = ""
    if server_dict[channel.server]['raidchannel_dict'][channel]['type'] == 'egg':
        raidtype = "egg"
        raidaction = "hatch"
    else:
        raidtype = "raid"
        raidaction = "end"
    if not server_dict[channel.server]['raidchannel_dict'][channel]['active']:
        timerstr += _("Beep Beep! This {raidtype}'s timer has already expired as of {expiry_time} ({expiry_time24})!").format(raidtype=raidtype,expiry_time=strftime("%I:%M %p", localexpire),expiry_time24=strftime("%H:%M", localexpire))
    else:
        if server_dict[channel.server]['raidchannel_dict'][channel]['manual_timer']:
            timerstr += _("Beep Beep! This {raidtype} will {raidaction} at {expiry_time} ({expiry_time24})!").format(raidtype=raidtype,raidaction=raidaction,expiry_time=strftime("%I:%M %p", localexpire),expiry_time24=strftime("%H:%M", localexpire))
        else:
            timerstr += _("Beep Beep! No one told me when the {raidtype} will {raidaction}, so I'm assuming it will {raidaction} at {expiry_time} ({expiry_time24})!").format(raidtype=raidtype,raidaction=raidaction,expiry_time=strftime("%I:%M %p", localexpire),expiry_time24=strftime("%H:%M", localexpire))

    return timerstr


async def _timerset(channel, exptime):
    exptime = int(exptime)
    # Clembot saves the timer message in the channel's 'exp' field.

    ticks = time.time()

    if server_dict[channel.server]['raidchannel_dict'][channel]['type'] == 'egg':
        raidtype = "Eggs"
    else:
        raidtype = "Raids"

    try:
        s = exptime * 60
        if s >= 3600:
            await Clembot.send_message(channel, _("Beep Beep...that's too long. {raidtype} currently last no more than one hour...").format(raidtype=raidtype))
            return
        if s < 0:
            await Clembot.send_message(channel, _("Beep Beep...I can't do that! No negative numbers, please!"))
            return
    except:
        await Clembot.send_message(channel, _("Beep Beep...I couldn't understand your time format..."))
        return
    expire = ticks + s


    # Update timestamp
    server_dict[channel.server]['raidchannel_dict'][channel]['exp'] = expire

    raid_expiry_time = fetch_channel_expire_time(channel)
    suggested_start_time = server_dict[channel.server]['raidchannel_dict'][channel]['suggested_start']
    is_raid_egg = server_dict[channel.server]['raidchannel_dict'][channel]['type'] == "egg"

    if suggested_start_time:
        if is_raid_egg:
            raid_expiry_time = raid_expiry_time + timedelta(hours=1)

        if suggested_start_time > raid_expiry_time:
            server_dict[channel.server]['raidchannel_dict'][channel]['suggested_start'] = False
            await Clembot.send_message(channel, _("Beep Beep! Start time is cleared as it was before raid ends!"))


    # Reactivate channel
    if not server_dict[channel.server]['raidchannel_dict'][channel]['active']:
        await Clembot.send_message(channel, "The channel has been reactivated.")
    server_dict[channel.server]['raidchannel_dict'][channel]['active'] = True
    # Mark that timer has been manually set
    server_dict[channel.server]['raidchannel_dict'][channel]['manual_timer'] = True
    # Send message
    timerstr = await print_raid_timer(channel)
    await Clembot.send_message(channel, timerstr)
    # Trigger expiry checking
    event_loop.create_task(expiry_check(channel))

@Clembot.command(pass_context=True)
@checks.raidchannel()
async def timerset(ctx):
    """Set the remaining duration on a raid.

    Usage: !timerset <minutes>
    Works only in raid channels, can be set or overridden by anyone.
    Clembot displays the end time in HH:MM local time."""
    try:
        if server_dict[ctx.message.channel.server]['raidchannel_dict'][ctx.message.channel]['type'] == 'exraid':
            await Clembot.send_message(ctx.message.channel, _("Timerset isn't supported for exraids. Please get a mod/admin to remove the channel if channel needs to be removed."))
            return
    except KeyError:
        pass
    args = ctx.message.content[10:]
    if args.isdigit():
        raidexp = args
    elif ":" in args:
        time = args
        h,m = re.sub(r"[a-zA-Z]", "", time).split(":",maxsplit=1)
        if h is "": h = "0"
        if m is "": m = "0"
        if h.isdigit() and m.isdigit():
            raidexp = 60 * int(h) + int(m)
        else:
            await Clembot.send_message(ctx.message.channel, "Beep Beep! I couldn't understand your time format. Try again like this: **!timerset <minutes>**")
            return
    if str(raidexp).isdigit():
        await _timerset(ctx.message.channel, raidexp)
    else:
        await Clembot.send_message(ctx.message.channel, _("Beep Beep... I couldn't understand your time format. Try again like this: **!timerset <minutes>**"))

@Clembot.command(pass_context=True)
@checks.raidchannel()
async def timer(ctx):
    """Have Clembot resend the expire time message for a raid.

    Usage: !timer
    The expiry time should have been previously set with !timerset."""
    if server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['type'] == 'exraid':
        await Clembot.send_message(ctx.message.channel, _("Exraids don't expire. Please get a mod/admin to remove the channel if channel needs to be removed."))
        return
    else:
        timerstr = await print_raid_timer(ctx.message.channel)
        await Clembot.send_message(ctx.message.channel, timerstr)



#=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-
# Code added for start time

def print_24_hour(timestamp):
    return timestamp.strftime("%I:%M %p")

def print_12_hour(timestamp):
    return timestamp.strftime("%I:%M %p")

def print_time(timestamp):
    return timestamp.strftime("%I:%M %p") + " (" + timestamp.strftime("%H:%M") + ")"

def convert_into_time(time_as_text):
    try:
        start_time = time.strptime(time_as_text, '%I:%M %p')
    except ValueError:
        # try:
        #     start_time = time.strptime(time_as_text, '%H:%M')
        # except ValueError:
        start_time = None

    return start_time


def fetch_channel_expire_time(channel) -> datetime:

    local_expire_secs = server_dict[channel.server]['raidchannel_dict'][channel]['exp']
    raid_expires_at = datetime.fromtimestamp(local_expire_secs)

    server_dict[channel.server]['raidchannel_dict'][channel]['expiry_timestamp'] = raid_expires_at

    return raid_expires_at


def convert_into_current_time(channel, time_hour_and_min_only):
    offset = server_dict[channel.server]['offset']
    current_time = datetime.utcnow() + timedelta(hours=offset)

    start_time = current_time.replace(hour=time_hour_and_min_only.tm_hour, minute=time_hour_and_min_only.tm_min)
    return start_time

def validate_raid_start_time(raid_starts_at, raid_reported_at, raid_expires_at):
    try:
        if raid_reported_at <= raid_starts_at <= raid_expires_at:
            return True
    except Exception as error:
        print(error)

    return False

async def validate_start_time(channel, start_time):

    raid_expires_at = fetch_channel_expire_time(channel)

    offset = server_dict[channel.server]['offset']
    current_datetime = datetime.utcnow() + timedelta(hours=offset)

    suggested_start_time = convert_into_current_time(channel, start_time)

    is_raid_egg = server_dict[channel.server]['raidchannel_dict'][channel]['type'] == "egg"

    #modified time for raidegg
    if is_raid_egg:
        current_datetime = raid_expires_at
        raid_expires_at = raid_expires_at + timedelta(hours=1)

    if suggested_start_time :
        if suggested_start_time > raid_expires_at:
            await Clembot.send_message(channel, ("Beep Beep...! start time cannot be after raid expiry time!"))
            return None
        elif suggested_start_time < current_datetime:
            if is_raid_egg:
                await Clembot.send_message(channel, ("Beep Beep...! start time cannot be before the egg hatches!"))
            else:
                await Clembot.send_message(channel, ("Beep Beep...! start time cannot be in past!"))
            return None
    else:
        return None

    return suggested_start_time

@Clembot.command(pass_context=True)
@checks.raidchannel()
async def start(ctx):
    """Set the remaining duration on a raid.

    Usage: !start <hh:mm>
    Works only in raid channels, can be set or overridden by anyone.
    Clembot displays the end time in HH:MM local time."""
    if ctx.message.channel in server_dict[ctx.message.server]['raidchannel_dict']:
        try:
            if server_dict[ctx.message.channel.server]['raidchannel_dict'][ctx.message.channel]['type'] == 'exraid':
                await Clembot.send_message(ctx.message.channel, _("start isn't supported for exraids."))
                return
        except KeyError:
            pass
        args = ctx.message.content.lstrip("!start ")
        start_time = convert_into_time(args)

        if start_time is None:
            await Clembot.send_message(ctx.message.channel, _("Beep Beep... I couldn't understand your time format. Try again like this: `!start HH:MM AM/PM`"))
            return

        raid_starts_at = await validate_start_time(ctx.message.channel, start_time)
        if raid_starts_at:
            try:
                server_dict[ctx.message.channel.server]['raidchannel_dict'][ctx.message.channel]['suggested_start'] = raid_starts_at
                await Clembot.send_message(ctx.message.channel, _("Beep Beep! {member} suggested the start time : {starttime}").format(member=ctx.message.author.mention, starttime=print_24_hour(raid_starts_at)))
            except Exception as error:
                print(error)
            return

async def print_start_time(channel):
    timerstr = ""
    if not server_dict[channel.server]['raidchannel_dict'][channel]['suggested_start']:
        timerstr = ("Beep Beep! No start time has been suggested for this raid!")
    else:
        start_time = server_dict[channel.server]['raidchannel_dict'][channel]['suggested_start']
        timerstr += _("Beep Beep! The suggested start time for this raid is {start_time}!").format(start_time=print_24_hour(start_time))

    return timerstr


#=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=--=-=-=-=-
"""
Behind-the-scenes functions for raid management.
Triggerable through commands or through emoji
"""
async def _maybe(message, count):
    trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']
    if count == 1:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is interested!").format(member=message.author.mention))
    else:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is interested with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.mention not in server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']:
        trainer_dict[message.author.mention] = {}
    trainer_dict[message.author.mention]['status'] = "maybe"
    trainer_dict[message.author.mention]['count'] = count
    server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict'] = trainer_dict

async def _coming(message, count):
    trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']

    if count == 1:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is on the way!").format(member=message.author.mention))
    else:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is on the way with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.mention not in trainer_dict:
        trainer_dict[message.author.mention] = {}
    trainer_dict[message.author.mention]['status'] = "omw"
    trainer_dict[message.author.mention]['count'] = count
    server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict'] = trainer_dict


async def _here(message, count):
    trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']
    if count == 1:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is at the raid!").format(member=message.author.mention))
    else:
        await Clembot.send_message(message.channel, _("Beep Beep! {member} is at the raid with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.mention not in trainer_dict:
        trainer_dict[message.author.mention] = {}
    trainer_dict[message.author.mention]['status'] = "waiting"
    trainer_dict[message.author.mention]['count'] = count
    server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict'] = trainer_dict

async def _cancel(message):
    author = message.author
    channel = message.channel
    server = message.server
    try:
        t_dict = server_dict[server]['raidchannel_dict'][channel]['trainer_dict'][author.mention]
    except KeyError:
        await Clembot.send_message(channel, _("Beep Beep! {member} has no status to cancel!").format(member=author.mention))

    if t_dict['status'] == "maybe":
        if t_dict['count'] == 1:
            await Clembot.send_message(channel, _("Beep Beep! {member} is no longer interested!").format(member=author.mention))
        else:
            await Clembot.send_message(channel, _("Beep Beep! {member} and their total of {trainer_count} trainers are no longer interested!").format(member=author.mention, trainer_count=t_dict['count']))
    if t_dict['status'] == "waiting":
        if t_dict['count'] == 1:
            await Clembot.send_message(channel, _("Beep Beep! {member} has left the raid!").format(member=author.mention))
        else:
            await Clembot.send_message(channel, _("Beep Beep! {member} and their total of {trainer_count} trainers have left the raid!").format(member=author.mention, trainer_count=t_dict['count']))
    if t_dict['status'] == "omw":
        if t_dict['count'] == 1:
            await Clembot.send_message(channel, _("Beep Beep! {member} is no longer on their way!").format(member=author.mention))
        else:
            await Clembot.send_message(channel, _("Beep Beep! {member} and their total of {trainer_count} trainers are no longer on their way!").format(member=author.mention, trainer_count=t_dict['count']))
    t_dict['status'] = None

@Clembot.event
async def on_message(message):
    if message.server is not None:
        raid_status = server_dict[message.server]['raidchannel_dict'].get(message.channel,None)
        if raid_status is not None:
            if server_dict[message.server]['raidchannel_dict'][message.channel]['active']:
                trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']
                if message.author.mention in trainer_dict:
                    count = trainer_dict[message.author.mention]['count']
                else:
                    count = 1
                omw_emoji = parse_emoji(message.server, config['omw_id'])
                if message.content.startswith(omw_emoji):
                    emoji_count = message.content.count(omw_emoji)
                    await _coming(message, emoji_count)
                    return
                here_emoji = parse_emoji(message.server, config['here_id'])
                if message.content.startswith(here_emoji):
                    emoji_count = message.content.count(here_emoji)
                    await _here(message, emoji_count)
                    return
                if "/maps" in message.content:
                    mapsindex = message.content.find("/maps")
                    newlocindex = message.content.rfind("http", 0, mapsindex)
                    if newlocindex == -1:
                        return
                    newlocend = message.content.find(" ", newlocindex)
                    if newlocend == -1:
                        newloc = message.content[newlocindex:]
                    else:
                        newloc = message.content[newlocindex:newlocend+1]
                    oldraidmsg = server_dict[message.server]['raidchannel_dict'][message.channel]['raidmessage']
                    oldreportmsg = server_dict[message.server]['raidchannel_dict'][message.channel]['raidreport']
                    oldembed = oldraidmsg.embeds[0]
                    newembed = discord.Embed(title=oldembed['title'],url=newloc,description=oldembed['description'],colour=discord.Colour(0x2ecc71))
                    newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
                    await Clembot.edit_message(oldraidmsg, new_content=oldraidmsg.content, embed=newembed)
                    await Clembot.edit_message(oldreportmsg, new_content=oldreportmsg.content, embed=newembed)
                    otw_list = []
                    trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']
                    for trainer in trainer_dict.keys():
                        if trainer_dict[trainer]['status']=='omw':
                            otw_list.append(trainer)
                    await Clembot.send_message(message.channel, content = _("Beep Beep! Someone has suggested a different location for the raid! Trainers {trainer_list}: make sure you are headed to the right place!").format(trainer_list=", ".join(otw_list)), embed = newembed)
                    return

    messagelist = message.content.split(" ")
    message.content = messagelist.pop(0).lower() + " " + " ".join(messagelist)
    await Clembot.process_commands(message)

@Clembot.command(pass_context=True)
@checks.citychannel()
@checks.raidset()
async def exraid(ctx):
    """Report an upcoming EX raid.

    Usage: !exraid <species> <location>
    Clembot will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in.
    Clembot's message will also include the type weaknesses of the boss.

    Finally, Clembot will create a separate channel for the raid report, for the purposes of organizing the raid."""

    await _exraid(ctx.message)

async def _exraid(message):
    args = message.clean_content[8:]
    args_split = args.split(" ")
    del args_split[0]
    if len(args_split) <= 1:
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!exraid <pokemon name> <location>**"))
        return
    entered_raid = re.sub("[\@]", "", args_split[0].lower())
    del args_split[0]
    if entered_raid not in pkmn_info['pokemon_list']:
        await Clembot.send_message(message.channel, spellcheck(entered_raid))
        return
    if entered_raid not in pkmn_info['raid_list'] and entered_raid in pkmn_info['pokemon_list']:
        await Clembot.send_message(message.channel, _("Beep Beep! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
        return

    raid_details = " ".join(args_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!exraid <pokemon name> <location>**"))
        return

    raid_gmaps_link = create_gmaps_query(raid_details, message.channel)

    raid_channel_name = entered_raid + "-" + sanitize_channel_name(raid_details)
    raid_channel_overwrites = message.channel.overwrites
    meowth_overwrite = (Clembot.user, discord.PermissionOverwrite(send_messages = True))
    for overwrite in raid_channel_overwrites:
        overwrite[1].send_messages = False
    raid_channel = await Clembot.create_channel(message.server, raid_channel_name, *raid_channel_overwrites, meowth_overwrite)
    raid = discord.utils.get(message.server.roles, name = entered_raid)
    if raid is None:
        raid = await Clembot.create_role(server = message.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "http://floatzel.net/pokemon/black-white/sprites/images/{0}.png".format(str(raid_number))
    raid_embed = discord.Embed(title=_("Beep Beep! Click here for directions to the EX raid!"),url=raid_gmaps_link,description=_("Weaknesses: {weakness_list}").format(weakness_list=weakness_to_str(message.server, get_weaknesses(entered_raid))),colour=discord.Colour(0x2ecc71))
    raid_embed.set_thumbnail(url=raid_img_url)
    raidreport = await Clembot.send_message(message.channel, content = _("Beep Beep! {pokemon} EX raid reported by {member}! Details: {location_details}. Send proof of your invite to this EX raid to an admin and coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
    await asyncio.sleep(1) #Wait for the channel to be created.

    raidmsg = _("""Beep Beep! {pokemon} EX raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!

To update your status, choose from the following commands:
**!interested, !coming, !here, !cancel**
If you are bringing more than one trainer/account, add the number of accounts total on your first status update.
Example: `!coming 5`

To see the list of trainers who have given their status:
**!list interested, !list coming, !list here**
Alternatively **!list** by itself will show all of the above.

**!location** will show the current raid location.
**!location new <address>** will let you correct the raid address.
Sending a Google Maps link will also update the raid location.

Message **!starting** when the raid is beginning to clear the raid's 'here' list.

This channel needs to be manually deleted!""").format(pokemon=raid.mention, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
    raidmessage = await Clembot.send_message(raid_channel, content = raidmsg, embed=raid_embed)

    server_dict[message.server]['raidchannel_dict'][raid_channel] = {
        'reportcity' : message.channel.name,
        'trainer_dict' : {},
        'exp' : None, # No expiry
        'manual_timer' : False,
        'active' : True,
        'raidmessage' : raidmessage,
        'raidreport' : raidreport,
        'address' : raid_details,
        'type' : 'exraid',
        'pokemon' : entered_raid,
        'egglevel' : '0',
        'suggested_start' : False
        }



    event_loop.create_task(expiry_check(raid_channel))

@Clembot.command(pass_context=True)
@checks.citychannel()
@checks.raidset()
async def raidegg(ctx):
    """Report a raid egg.

    Usage: !raidegg <level> <location> <minutes>

    Clembot will give a map link to the entered location and create a channel for organising the coming raid in.
    Clembot will also provide info on the possible bosses that can hatch and their types.

    <level> - Required. Level of the egg. Levels are from 1 to 5.
    <location> - Required. Address/Location of the gym.
    <minutes-remaining> - Not required. Time remaining until the egg hatches into an open raid. 1-60 minutes will be accepted. If not provided, 1 hour is assumed. Whole numbers only."""
    await _raidegg(ctx.message)

async def _raidegg(message):
    args = message.clean_content[8:]
    args_split = args.split(" ")
    del args_split[0]
    if len(args_split) <= 1:
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Usage: **!raidegg <level> <location>**"))
        return

    if args_split[0].isdigit():
        egg_level = int(args_split[0])
        del args_split[0]
    else:
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info."))
        return

    if args_split[-1].isdigit():
        raidexp = args_split[-1]
        del args_split[-1]
    elif ":" in args_split[-1]:
        args_split[-1] = re.sub(r"[a-zA-Z]", "", args_split[-1])
        if args_split[-1].split(":")[0] == "":
            endhours = 0
        else:
            endhours = int(args_split[-1].split(":")[0])
        if args_split[-1].split(":")[1] == "":
            endmins = 0
        else:
            endmins = int(args_split[-1].split(":")[1])
        raidexp = 60 * endhours + endmins
        del args_split[-1]
    else:
        raidexp = False



    raid_details = " ".join(args_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Clembot.send_message(message.channel, _("Beep Beep! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info."))
        return

    raid_gmaps_link = create_gmaps_query(raid_details, message.channel)

    if egg_level > 5 or egg_level == 0:
        await Clembot.send_message(message.channel, _("Beep Beep! Raid egg levels are only from 1-5!"))
        return
    else:
        egg_level = str(egg_level)
        egg_info = raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_list = ""
        mon_in_one_line = 0
        for p in egg_info['pokemon']:
            p_name = get_name(p)
            p_type = get_type(message.server, p)
            mon_in_one_line = mon_in_one_line + 1
            if (mon_in_one_line == 1):
                separator = " "
            else:
                separator = "**\\**"
            boss_list += (separator + " **" + p_name + "** " + ''.join(p_type) + " ")
        raid_channel_name = "level-" + egg_level + "-egg-" + sanitize_channel_name(raid_details)
        raid_channel = await Clembot.create_channel(message.server, raid_channel_name, *message.channel.overwrites)
        raid_img_url = "https://raw.githubusercontent.com/apavlinovic/pokemon-go-imagery/master/images/{}".format(str(egg_img))
        raid_embed = discord.Embed(title=_("Beep Beep! Click here for directions to the coming raid!"),url=raid_gmaps_link,description=_("Possible Bosses: {boss_list}").format(boss_list=boss_list),colour=discord.Colour(0x2ecc71))
        raid_embed.set_thumbnail(url=raid_img_url)
        raidreport = await Clembot.send_message(message.channel, content = _("Beep Beep! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}").format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        await asyncio.sleep(1) #Wait for the channel to be created.

        raidmsg = _("""Beep Beep! Level {level} raid egg reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!
When this egg raid expires, there will be 15 minutes to update it into an open raid before it'll be deleted.
** **
Please type `!beep` if you need a refresher of Clembot commands! 
""").format(
            level=egg_level, member=message.author.mention, citychannel=message.channel.mention,
            location_details=raid_details)

        #         raidmsg = _("""Beep Beep! Level {level} raid egg reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!
        #
        # Message **!interested** if you're interested in attending.
        # If you are interested in bringing more than one trainer/account, add in the number at the end of the commend.
        # Example: `!interested 5`
        #
        # Use **!list interested** to see the list of trainers who are interested.
        #
        # **!location** will show the current raid location.
        # **!location new <address>** will let you correct the raid address.
        # Sending a Google Maps link will also update the raid location.
        #
        # **!timer** will show how long until the egg catches into an open raid.
        # **!timerset** will let you correct the egg countdown time.
        #
        # Message **!raid <pokemon>** to update this channel into an open raid.
        # Message **!raid assume <pokemon>** to have the channel auto-update into an open raid.
        #
        # When this egg raid expires, there will be 15 minutes to update it into an open raid before it'll be deleted.""").format(level=egg_level, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
        raidmessage = await Clembot.send_message(raid_channel, content = raidmsg, embed=raid_embed)
        server_dict[message.server]['raidchannel_dict'][raid_channel] = {
            'reportcity' : message.channel.name,
            'trainer_dict' : {},
            'exp' : time.time() + 60 * 60, # One hour from now
            'manual_timer' : False, # No one has explicitly set the timer, Clembot is just assuming 2 hours
            'active' : True,
            'raidmessage' : raidmessage,
            'raidreport' : raidreport,
            'address' : raid_details,
            'type' : 'egg',
            'pokemon' : '',
            'egglevel' : egg_level,
            'suggested_start' : False
            }

        if raidexp:
            await _timerset(raid_channel,raidexp)
        else:
            await Clembot.send_message(raid_channel, content = _("Beep Beep! Hey {member}, if you can, set the time left on the raid using **!timerset <minutes>** so others can check it with **!timer**.").format(member=message.author.mention))

        event_loop.create_task(expiry_check(raid_channel))


async def _eggassume(args, raid_channel):
    eggdetails = server_dict[raid_channel.server]['raidchannel_dict'][raid_channel]
    egglevel = eggdetails['egglevel']
    if config['allow_assume'][egglevel] == "False":
        await Clembot.send_message(raid_channel, _("Beep Beep! **!raid assume** is not allowed in this level egg."))
        return
    entered_raid = re.sub("[\@]", "", args.lstrip("assume").lstrip(" ").lower())
    if entered_raid not in pkmn_info['pokemon_list']:
        await Clembot.send_message(raid_channel, spellcheck(entered_raid))
        return
    else:
        if entered_raid not in pkmn_info['raid_list']:
            await Clembot.send_message(raid_channel, _("Beep Beep! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
            return
        else:
            if get_number(entered_raid) not in raid_info['raid_eggs'][egglevel]['pokemon']:
                await Clembot.send_message(raid_channel, _("Beep Beep! The Pokemon {pokemon} does not hatch from level {level} raid eggs!").format(pokemon=entered_raid.capitalize(), level=egglevel))
                return

    eggdetails['pokemon'] = entered_raid
    raidrole = discord.utils.get(raid_channel.server.roles, name = entered_raid)
    if raidrole is None:
        raidrole = await Clembot.create_role(server = raid_channel.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    await Clembot.send_message(raid_channel, _("Beep Beep! This egg will be assumed to be {pokemon} when it hatches!").format(pokemon=raidrole.mention))
    return

async def _eggtoraid(entered_raid, raid_channel):
    eggdetails = server_dict[raid_channel.server]['raidchannel_dict'][raid_channel]
    egglevel = eggdetails['egglevel']
    manual_timer = eggdetails['manual_timer']
    trainer_dict = eggdetails['trainer_dict']
    reportcity = eggdetails['reportcity']
    reportcitychannel = discord.utils.get(raid_channel.server.channels, name=reportcity)
    egg_address = eggdetails['address']
    egg_report = eggdetails['raidreport']
    raid_message = eggdetails['raidmessage']
    raid_messageauthor = raid_message.mentions[0]
    raidexp = eggdetails['exp'] + 60 * 60
    suggested_start = eggdetails['suggested_start']
    if entered_raid not in pkmn_info['pokemon_list']:
        await Clembot.send_message(raid_channel, spellcheck(entered_raid))
        return
    else:
        if entered_raid not in pkmn_info['raid_list']:
            await Clembot.send_message(raid_channel, _("Beep Beep! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
            return
        else:
            if get_number(entered_raid) not in raid_info['raid_eggs'][egglevel]['pokemon']:
                await Clembot.send_message(raid_channel, _("Beep Beep! The Pokemon {pokemon} does not hatch from level {level} raid eggs!").format(pokemon=entered_raid.capitalize(), level=egglevel))
                return

    raid_channel_name = raid_channel.name.replace(('level-{egglevel}-egg').format(egglevel=egglevel),entered_raid)
    oldembed = raid_message.embeds[0]
    raid_gmaps_link = oldembed['url']

    raid = discord.utils.get(raid_channel.server.roles, name = entered_raid)
    if raid is None:
        raid = await Clembot.create_role(server = raid_channel.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)

    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "http://floatzel.net/pokemon/black-white/sprites/images/{0}.png".format(str(raid_number))
    raid_embed = discord.Embed(title=_("Beep Beep! Click here for directions to the raid!"),url=raid_gmaps_link,description=_("Weaknesses: {weakness_list}").format(weakness_list=weakness_to_str(raid_channel.server, get_weaknesses(entered_raid))),colour=discord.Colour(0x2ecc71))
    raid_embed.set_thumbnail(url=raid_img_url)
    raidreportcontent = _("Beep Beep! The egg has hatched into a {pokemon} raid! Details: {location_details}. Coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), location_details=egg_address, raid_channel=raid_channel.mention)
    await Clembot.edit_channel(raid_channel, name=raid_channel_name)
    raidmsg = _("""Beep Beep! The egg reported by {member} in {citychannel} hatched into a {pokemon} raid! Details: {location_details}. Coordinate here!
    This channel will be deleted five minutes after the timer expires.
    ** **
    Please type `!beep` if you need a refresher of Clembot commands! 
    """).format(
        member=raid_messageauthor.mention,
    citychannel=reportcitychannel.mention,
    pokemon=entered_raid.capitalize(),
    location_details=egg_address)

#     raidmsg = _("""Beep Beep! The egg reported by {member} in {citychannel} hatched into a {pokemon} raid! Details: {location_details}. Coordinate here!
#
# To update your status, choose from the following commands:
# **!interested, !coming, !here, !cancel**
# If you are bringing more than one trainer/account, add the number of accounts total on your first status update.
# Example: `!coming 5`
#
# To see the list of trainers who have given their status:
# **!list interested, !list coming, !list here**
# Alternatively **!list** by itself will show all of the above.
#
# **!location** will show the current raid location.
# **!location new <address>** will let you correct the raid address.
# Sending a Google Maps link will also update the raid location.
#
# **!timer** will show the current raid time.
# **!timerset** will let you correct the raid countdown time.
#
# Message **!starting** when the raid is beginning to clear the raid's 'here' list.
#
# This channel will be deleted five minutes after the timer expires.""").format(member=raid_messageauthor.mention,
#                                                                               citychannel=reportcitychannel.mention,
#                                                                               pokemon=entered_raid.capitalize(),
#                                                                               location_details=egg_address)

    try:
        raid_message = await Clembot.edit_message(raid_message, new_content=raidmsg, embed=raid_embed)
    except discord.errors.NotFound:
        pass
    try:
        egg_report = await Clembot.edit_message(egg_report, new_content=raidreportcontent, embed=raid_embed)
    except discord.errors.NotFound:
        pass

    server_dict[raid_channel.server]['raidchannel_dict'][raid_channel] = {
    'reportcity' : reportcity,
    'trainer_dict' : trainer_dict,
    'exp' : raidexp,
    'manual_timer' : manual_timer,
    'active' : True,
    'raidmessage' : raid_message,
    'raidreport' : egg_report,
    'address' : egg_address,
    'type' : 'raid',
    'pokemon' : entered_raid,
    'egglevel' : '0',
    'suggested_start' : suggested_start
    }

    trainer_list = []
    trainer_dict = server_dict[raid_channel.server]['raidchannel_dict'][raid_channel]['trainer_dict']
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status'] =='maybe' or trainer_dict[trainer]['status'] =='omw' or trainer_dict[trainer]['status'] =='waiting':
            trainer_list.append(trainer)
    await Clembot.send_message(raid_channel, content = _("Beep Beep! Trainers {trainer_list}: The raid egg has just hatched into a {pokemon} raid!\nYou're now able to update your status with **!coming** or **!here**. If you've changed your plans, use **!cancel**.").format(trainer_list=", ".join(trainer_list), pokemon=raid.mention), embed = raid_embed)

    event_loop.create_task(expiry_check(raid_channel))


@Clembot.command(pass_context=True, aliases=["b"])
@checks.activeraidchannel()
async def beep(ctx):
    raidmsg = _("""
{member} to update your status, choose from the following commands:
** **
`!interested`, `!coming`, `!here` or `!cancel`
or alternatively use the shortcuts 
`!i`, `!c`, `!h` or `!x`
** **
If you are bringing more than one trainer/account, add the number of accounts total on your first status update.
Example: `!coming 5` or `!c 5`
** **
`!list` or `!l` will show the list of trainers who have given their status.
** **
`!location` will show the current raid location.
`!location new <address>` will let you correct the raid address.
*Sending a Google Maps link will also update the raid location.*
** **
`!timer` will show the current raid time.
`!timerset` will let you correct the raid countdown time.
** **
`!start HH:MM AM/PM` to suggest a start time.
`!starting` when the raid is beginning to clear the raid's 'here' list.""").format(member=ctx.message.author.mention)
    await Clembot.send_message(ctx.message.channel, content=raidmsg)


@Clembot.command(pass_context=True, aliases=["i", "maybe"])
@checks.activeraidchannel()
async def interested(ctx, *, count: str = None):
    """Indicate you are interested in the raid.

    Usage: !interested [message]
    Works only in raid channels. If message is omitted, assumes you are a group of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']
    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Clembot.send_message(ctx.message.channel, _("Beep Beep! I can't understand how many are in your group. Just say **!interested** if you're by yourself, or **!interested 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.mention in trainer_dict:
            count = trainer_dict[ctx.message.author.mention]['count']
        else:
            count = 1

    await _maybe(ctx.message, count)


@Clembot.command(pass_context=True, aliases=["c"])
@checks.activeraidchannel()
async def coming(ctx, *, count: str = None):
    """Indicate you are on the way to a raid.

    Usage: !coming [message]
    Works only in raid channels. If message is omitted, checks for previous !maybe
    command and takes the count from that. If it finds none, assumes you are a group
    of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    try:
        if server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['type'] == "egg":
            if server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['pokemon'] == "":
                await Clembot.send_message(ctx.message.channel, _("Beep Beep! Please wait until the raid egg has hatched before announcing you're coming or present."))
                return
    except:
        pass

    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']

    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Clembot.send_message(ctx.message.channel, _("Beep Beep! I can't understand how many are in your group. Just say **!coming** if you're by yourself, or **!coming 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.mention in trainer_dict:
            count = trainer_dict[ctx.message.author.mention]['count']
        else:
            count = 1

    await _coming(ctx.message, count)

@Clembot.command(pass_context=True, aliases=["h"])
@checks.activeraidchannel()
async def here(ctx, *, count: str = None):
    """Indicate you have arrived at the raid.

    Usage: !here [message]
    Works only in raid channels. If message is omitted, and
    you have previously issued !coming, then preserves the count
    from that command. Otherwise, assumes you are a group of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    try:
        if server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['type'] == "egg":
            if server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['pokemon'] == "":
                await Clembot.send_message(ctx.message.channel, _("Beep Beep! Please wait until the raid egg has hatched before announcing you're coming or present."))
                return
    except:
        pass

    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']

    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Clembot.send_message(ctx.message.channel, _("Beep Beep! I can't understand how many are in your group. Just say **!here** if you're by yourself, or **!coming 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.mention in trainer_dict:
            count = trainer_dict[ctx.message.author.mention]['count']
        else:
            count = 1

    await _here(ctx.message, count)

@Clembot.command(pass_context=True, aliases=["x"])
@checks.activeraidchannel()
async def cancel(ctx):
    """Indicate you are no longer interested in a raid.

    Usage: !cancel
    Works only in raid channels. Removes you and your party
    from the list of trainers who are "otw" or "here"."""
    await _cancel(ctx.message)

@Clembot.command(pass_context=True)
@checks.activeraidchannel()
async def starting(ctx):
    """Signal that a raid is starting.

    Usage: !starting
    Works only in raid channels. Sends a message and clears the waiting list. Users who are waiting
    for a second group must reannounce with the :here: emoji or !here."""

    ctx_startinglist = []

    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']

    # Add all waiting trainers to the starting list
    for trainer in trainer_dict:
        if trainer_dict[trainer]['status'] == "waiting":
            ctx_startinglist.append(trainer)

    # Go back and delete the trainers from the waiting list
    for trainer in ctx_startinglist:
        del trainer_dict[trainer]
    server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict'] = trainer_dict
    server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['suggested_start'] = False

    starting_str = _("Beep Beep! The group that was waiting is starting the raid! Trainers {trainer_list}, please respond with {here_emoji} or **!here** if you are waiting for another group!").format(trainer_list=", ".join(ctx_startinglist), here_emoji=parse_emoji(ctx.message.server, config['here_id']))
    if len(ctx_startinglist) == 0:
        starting_str = _("Beep Beep! How can you start when there's no one waiting at this raid!?")
    await Clembot.send_message(ctx.message.channel, starting_str)

@Clembot.group(pass_context=True, aliases=["lists"])
@checks.cityraidchannel()
@checks.raidset()
async def list(ctx):
    """Lists all raid info for the current channel.

    Usage: !list
    Works only in raid or city channels. Calls the interested, waiting, and here lists. Also prints
    the raid timer. In city channels, lists all active raids."""

    if ctx.invoked_subcommand is None:
        listmsg = ""
        server = ctx.message.server
        channel = ctx.message.channel
        if checks.check_citychannel(ctx):
            activeraidnum = 0
            cty = channel.name
            rc_d = server_dict[server]['raidchannel_dict']
            listmsg += (_("Beep Beep! Current Raids for {0}:").format(cty.capitalize()))

            for r in server_dict[server]['raidchannel_dict']:
                ctx_waitingcount = 0
                ctx_omwcount = 0
                ctx_maybecount = 0
                #sorted(type_eff.items(), key=lambda x: x[1], reverse=True)
                if rc_d[r]['reportcity'] == cty and rc_d[r]['active'] and discord.utils.get(server.channels, id=r.id):
                    for trainer in rc_d[r]['trainer_dict'].values():
                        if trainer['status'] == "waiting":
                            ctx_waitingcount += trainer['count']
                        elif trainer['status'] == "omw":
                            ctx_omwcount += trainer['count']
                        elif trainer['status'] == "maybe":
                            ctx_maybecount += trainer['count']
                    if rc_d[r]['type'] == 'exraid':
                        localexpire = "No expiry"
                        assumed_str = " (EXraid)"
                    else:
                        localexpire = strftime("%I:%M %p", time.gmtime(rc_d[r]['exp'] + 3600 * server_dict[server]['offset']))
                        if rc_d[r]['manual_timer'] == False:
                            assumed_str = " (assumed)"
                        else:
                            assumed_str = ""
                    suggest_starttime = "not set yet!"
                    if rc_d[r]['suggested_start'] == False:
                        suggest_starttime = "not set yet!"
                    else:
                        suggest_starttime = print_24_hour(rc_d[r]['suggested_start'])
                    listmsg += (_("\n{raidchannel} - {interestcount} interested, {comingcount} coming, {herecount} here. End time: {expiry}{manualtimer}. Suggested start time: {suggest_starttime}").format(raidchannel=r.mention, interestcount=ctx_maybecount, comingcount=ctx_omwcount, herecount=ctx_waitingcount, expiry=localexpire, manualtimer=assumed_str,suggest_starttime=suggest_starttime))
                    activeraidnum += 1
            if activeraidnum == 0:
                await Clembot.send_message(channel, _("Beep Beep! No active raids! Report one with **!raid <name> <location>**."))
                return
            else:
                await Clembot.send_message(channel, listmsg)
                return

        if checks.check_raidchannel(ctx):
            if checks.check_raidactive(ctx):
                rc_d = server_dict[server]['raidchannel_dict'][channel]
                if rc_d['type'] == 'egg' and rc_d['pokemon'] == '':
                    listmsg += await _interest(ctx)
                    listmsg += "\n"
                    listmsg += await print_raid_timer(channel)
                    listmsg += "\n" + await print_start_time(channel)
                else:
                    listmsg += await _interest(ctx)
                    listmsg += "\n" + await _otw(ctx)
                    listmsg += "\n" + await _waiting(ctx)
                    if rc_d['type'] != 'exraid':
                        listmsg += "\n" + await print_raid_timer(channel)
                    listmsg += "\n" + await print_start_time(channel)
                await Clembot.send_message(channel, listmsg)
                return

@Clembot.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def omw(ctx):
    await Clembot.send_message(ctx.message.channel, content = _("Beep Beep! Hey {member}, I don't know if you meant **!coming** to say that you are coming or **!list coming** to see the other trainers on their way").format(member=ctx.message.author.mention))

@list.command(pass_context=True)
@checks.activeraidchannel()
async def interested(ctx):
    """Lists the number and users who are interested in the raid.

    Usage: !list interested
    Works only in raid channels."""
    listmsg = await _interest(ctx)
    await Clembot.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def coming(ctx):
    """Lists the number and users who are coming to a raid.

    Usage: !list coming
    Works only in raid channels."""
    listmsg = await _otw(ctx)
    await Clembot.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def here(ctx):
    """List the number and users who are present at a raid.

    Usage: !list here
    Works only in raid channels."""
    listmsg = await _waiting(ctx)
    await Clembot.send_message(ctx.message.channel, listmsg)

@Clembot.command(pass_context=True)
@commands.has_permissions(manage_server=True)
@checks.raidchannel()
async def clearstatus(ctx):
    """Clears raid channel status lists.

    Usage: !clearstatus
    Only usable by admins."""
    try:
        server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict'] = {}
        await Clembot.send_message(ctx.message.channel, "Beep Beep! Raid status lists have been cleared!")
    except KeyError:
        pass

@Clembot.command(pass_context=True)
@checks.activeraidchannel()
async def duplicate(ctx):
    """A command to report a raid channel as a duplicate.

    Usage: !duplicate
    Works only in raid channels. When three users report a channel as a duplicate,
    Clembot deactivates the channel and marks it for deletion."""
    channel = ctx.message.channel
    author = ctx.message.author
    server = ctx.message.server
    rc_d = server_dict[server]['raidchannel_dict'][channel]
    t_dict =rc_d['trainer_dict']
    can_manage = channel.permissions_for(author).manage_channels

    if can_manage:
        dupecount = 2
        rc_d['duplicate'] = dupecount
    else:
        if author in t_dict:
            try:
                if t_dict[author]['dupereporter']:
                    dupeauthmsg = await Clembot.send_message(channel, _("Beep Beep! You've already made a duplicate report for this raid!"))
                    await asyncio.sleep(10)
                    await Clembot.delete_message(dupeauthmsg)
                    return
                else:
                    t_dict[author]['dupereporter'] = True
            except KeyError:
                t_dict[author]['dupereporter'] = True
        else:
            t_dict[author] = {
                'status' : '',
                'dupereporter' : True
                }
        try:
            dupecount = rc_d['duplicate']
        except KeyError:
            dupecount = 0
            rc_d['duplicate'] = dupecount

    dupecount += 1
    rc_d['duplicate'] = dupecount

    if dupecount >= 3:
        rusure = await Clembot.send_message(channel, _("Beep Beep! Are you sure you wish to remove this raid?"))
        await Clembot.add_reaction(rusure, "✅") #checkmark
        await Clembot.add_reaction(rusure, "❎") #cross
        def check(react,user):
            if user.id != author.id:
                return False
            return True

        res = await Clembot.wait_for_reaction(['✅', '❎'], message=rusure, check=check, timeout=60)

        if res is not None:
            if res.reaction.emoji == "❎":
                await Clembot.delete_message(rusure)
                confirmation = await Clembot.send_message(channel, _("Duplicate Report cancelled."))
                logger.info("Duplicate Report - Cancelled - "+channel.name+" - Report by "+author.name)
                dupecount = 2
                server_dict[server]['raidchannel_dict'][channel]['duplicate'] = dupecount
                await asyncio.sleep(10)
                await Clembot.delete_message(confirmation)
                return
            elif res.reaction.emoji == "✅":
                await Clembot.delete_message(rusure)
                await Clembot.send_message(channel, "Duplicate Confirmed")
                logger.info("Duplicate Report - Channel Expired - "+channel.name+" - Last Report by "+author.name)
                await expire_channel(channel)
                return
        else:
            await Clembot.delete_message(rusure)
            confirmation = await Clembot.send_message(channel, _("Duplicate Report Timed Out."))
            logger.info("Duplicate Report - Timeout - "+channel.name+" - Report by "+author.name)
            dupecount = 2
            server_dict[server]['raidchannel_dict'][channel]['duplicate'] = dupecount
            await asyncio.sleep(10)
            await Clembot.delete_message(confirmation)
    else:
        rc_d['duplicate'] = dupecount
        confirmation = await Clembot.send_message(channel, _("Duplicate report #{duplicate_report_count} received.").format(duplicate_report_count=str(dupecount)))
        logger.info("Duplicate Report - "+channel.name+" - Report #"+str(dupecount)+ "- Report by "+author.name)
        return

@Clembot.group(pass_context=True)
@checks.activeraidchannel()
async def location(ctx):
    """Get raid location.

    Usage: !location
    Works only in raid channels. Gives the raid location link."""
    if ctx.invoked_subcommand is None:
        message = ctx.message
        server = message.server
        channel = message.channel
        rc_d = server_dict[server]['raidchannel_dict']
        raidmsg = rc_d[channel]['raidmessage']
        location = rc_d[channel]['address']
        report_city = rc_d[channel]['reportcity']
        report_channel = discord.utils.get(server.channels, name=report_city)
        locurl = create_gmaps_query(location, report_channel)
        oldembed = raidmsg.embeds[0]
        newembed = discord.Embed(title=oldembed['title'],url=locurl,description=oldembed['description'],colour=discord.Colour(0x2ecc71))
        newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
        await Clembot.send_message(channel, content = _("Beep Beep! Here's the current location for the raid!\nDetails:{location}").format(location = location), embed = newembed)

@location.command(pass_context=True)
@checks.activeraidchannel()
async def new(ctx):
    """Change raid location.

    Usage: !location new <new address>
    Works only in raid channels. Changes the google map links."""

    message = ctx.message
    space1 = message.content.find(" ",13)
    if space1 == -1:
        await Clembot.send_message(message.channel, _("Beep Beep! We're missing the new location details! Usage: **!location new <new address>**"))
        return
    else:
        report_city = server_dict[message.server]['raidchannel_dict'][message.channel]['reportcity']
        report_channel = discord.utils.get(message.server.channels, name=report_city)

        details = message.content[space1:]
        if "/maps" in message.content:
            mapsindex = message.content.find("/maps")
            newlocindex = message.content.rfind("http", 0, mapsindex)
            if newlocindex == -1:
                return
            newlocend = message.content.find(" ", newlocindex)
            if newlocend == -1:
                newloc = message.content[newlocindex:]
            else:
                newloc = message.content[newlocindex:newlocend+1]
        else:
            newloc = create_gmaps_query(details, report_channel)

        server_dict[message.server]['raidchannel_dict'][message.channel]['address'] = details
        oldraidmsg = server_dict[message.server]['raidchannel_dict'][message.channel]['raidmessage']
        oldreportmsg = server_dict[message.server]['raidchannel_dict'][message.channel]['raidreport']
        oldembed = oldraidmsg.embeds[0]
        newembed = discord.Embed(title=oldembed['title'],url=newloc,description=oldembed['description'],colour=discord.Colour(0x2ecc71))
        newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
        newraidmsg = await Clembot.edit_message(oldraidmsg, new_content=oldraidmsg.content, embed=newembed)
        newreportmsg = await Clembot.edit_message(oldreportmsg, new_content=oldreportmsg.content, embed=newembed)
        server_dict[message.server]['raidchannel_dict'][message.channel]['raidmessage'] = newraidmsg
        server_dict[message.server]['raidchannel_dict'][message.channel]['raidreport'] = newreportmsg
        otw_list = []
        trainer_dict = server_dict[message.server]['raidchannel_dict'][message.channel]['trainer_dict']
        for trainer in trainer_dict.keys():
            if trainer_dict[trainer]['status']=='omw':
                otw_list.append(trainer)
        await Clembot.send_message(message.channel, content = _("Beep Beep! Someone has suggested a different location for the raid! Trainers {trainer_list}: make sure you are headed to the right place!").format(trainer_list=", ".join(otw_list)), embed = newembed)
        return

async def _interest(ctx):

    ctx_maybecount = 0

    # Grab all trainers who are maybe and sum
    # up their counts
    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']
    for trainer in trainer_dict.values():
        if trainer['status'] == "maybe":
            ctx_maybecount += trainer['count']

    # If at least 1 person is interested,
    # add an extra message indicating who it is.
    maybe_exstr = ""
    maybe_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='maybe':
            maybe_list.append(trainer)
    if ctx_maybecount > 0:
        maybe_exstr = _(" including {trainer_list} and the people with them! Let them know if there is a group forming").format(trainer_list=", ".join(maybe_list))
    listmsg = (_("Beep Beep! {trainer_count} interested{including_string}!").format(trainer_count=str(ctx_maybecount), including_string=maybe_exstr))

    return listmsg

async def _otw(ctx):

    ctx_omwcount = 0

    # Grab all trainers who are :omw: and sum
    # up their counts
    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']
    for trainer in trainer_dict.values():
        if trainer['status'] == "omw":
            ctx_omwcount += trainer['count']

    # If at least 1 person is on the way,
    # add an extra message indicating who it is.
    otw_exstr = ""
    otw_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='omw':
            otw_list.append(trainer)
    if ctx_omwcount > 0:
        otw_exstr = _(" including {trainer_list} and the people with them! Be considerate and wait for them if possible").format(trainer_list=", ".join(otw_list))
    listmsg = (_("Beep Beep! {trainer_count} on the way{including_string}!").format(trainer_count=str(ctx_omwcount), including_string=otw_exstr))
    return listmsg

async def _waiting(ctx):

    ctx_waitingcount = 0

    # Grab all trainers who are :here: and sum
    # up their counts
    trainer_dict = server_dict[ctx.message.server]['raidchannel_dict'][ctx.message.channel]['trainer_dict']
    for trainer in trainer_dict.values():
        if trainer['status'] == "waiting":
            ctx_waitingcount += trainer['count']

    # If at least 1 person is waiting,
    # add an extra message indicating who it is.
    waiting_exstr = ""
    waiting_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='waiting':
            waiting_list.append(trainer)
    if ctx_waitingcount > 0:
        waiting_exstr = _(" including {trainer_list} and the people with them! Be considerate and let them know if and when you'll be there").format(trainer_list=", ".join(waiting_list))
    listmsg = (_("Beep Beep! {trainer_count} waiting at the raid{including_string}!").format(trainer_count=str(ctx_waitingcount), including_string=waiting_exstr))
    return listmsg

@Clembot.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def interest(ctx):
    await Clembot.send_message(ctx.message.channel, _("Beep Beep! We've moved this command to **!list interested**."))

@Clembot.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def otw(ctx):
    await Clembot.send_message(ctx.message.channel, _("Beep Beep! We've moved this command to **!list coming**."))

@Clembot.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def waiting(ctx):
    await Clembot.send_message(ctx.message.channel, _("Beep Beep! We've moved this command to **!list here**."))

@Clembot.command(pass_context=True)
@checks.citychannel()
async def invite(ctx):
    """Join an EXraid by showing your invite.

    Usage: !invite *image attachment*
    If the image isn't added at the same time as the command, Clembot will wait 30 seconds for a followup message containing the image."""
    if ctx.message.attachments:
        await _invite(ctx)
    else:
        wait_msg = await Clembot.send_message(ctx.message.channel, _("Beep Beep! I'll wait for you to send your pass!"))
        def check(msg):
            if msg.channel == ctx.message.channel and ctx.message.author.id == msg.author.id:
                if msg.attachments:
                    return True
        invitemsg = await Clembot.wait_for_message(author = ctx.message.author, check=check, timeout=30)
        if invitemsg is not None:
            ctx.message = invitemsg
            await _invite(ctx)
            return
        else:
            await Clembot.delete_message(wait_msg)
            await Clembot.send_message(ctx.message.channel, "Beep Beep! You took too long to show me a screenshot of your invite! Retry when you're ready.")
            return

async def _invite(ctx):
    if 'https://cdn.discordapp.com' in ctx.message.attachments[0]['url']:
        if 'png' in ctx.message.attachments[0]['url'].lower() or 'jpg' in ctx.message.attachments[0]['url'].lower():
            fd = requests.get(ctx.message.attachments[0]['url'])
            img = Image.open(BytesIO(fd.content))
            width, height = img.size
            new_height = 3500
            new_width  = int(new_height * width / height)
            img = img.resize((new_width, new_height), Image.BICUBIC)
            img = img.filter(ImageFilter.EDGE_ENHANCE)
            enh = ImageEnhance.Brightness(img)
            img = enh.enhance(0.4)
            enh = ImageEnhance.Contrast(img)
            img = enh.enhance(4)
            txt = pytesseract.image_to_string(img, config=tesseract_config)
            if 'EX Raid Battle' or "This is a reward" or "Please visit the Gym" in txt:
                exraidlist = ''
                exraid_dict = {}
                exraidcount = 0
                for channel in server_dict[ctx.message.server]['raidchannel_dict']:
                    if not discord.utils.get(ctx.message.server.channels, id = channel.id):
                        continue
                    if server_dict[ctx.message.server]['raidchannel_dict'][channel]['type'] == 'exraid':
                        if channel.mention != '#deleted-channel':
                            exraidcount += 1
                            exraidlist += '\n' + str(exraidcount) + '.   ' + channel.mention
                            exraid_dict[str(exraidcount)] = channel
                if exraidcount > 0:
                    await Clembot.send_message(ctx.message.channel, "Beep Beep! {0}, it looks like you've got an EX Raid invitation! The following {1} EX Raids have been reported: \n {2} \n Reply with the number of the EX Raid you have been invited to. If none of them match your invite, type 'N' and report it with **!exraid**".format(ctx.message.author.mention, str(exraidcount), exraidlist))
                    reply = await Clembot.wait_for_message(author=ctx.message.author)
                    if reply.content.lower() == 'n':
                        await Clembot.send_message(ctx.message.channel, "Beep Beep! Be sure to report your EX Raid with **!exraid**!")
                    elif not reply.content.isdigit() or int(reply.content) > exraidcount:
                        await Clembot.send_message(ctx.message.channel, "Beep Beep! I couldn't tell which EX Raid you meant! Try the **!invite** command again, and make sure you respond with the number of the channel that matches!")
                    elif int(reply.content) <= exraidcount and int(reply.content) > 0:
                        overwrite = discord.PermissionOverwrite()
                        overwrite.send_messages = True
                        overwrite.read_messages = True
                        exraid_channel = exraid_dict[str(int(reply.content))]
                        await Clembot.edit_channel_permissions(exraid_channel, ctx.message.author, overwrite)
                        await Clembot.send_message(ctx.message.channel, "Beep Beep! Alright {0}, you can now send messages in {1}! Make sure you let the trainers in there know if you can make it to the EX Raid!".format(ctx.message.author.mention, exraid_channel.mention))
                    else:
                        await Clembot.send_message(ctx.message.channel, "Beep Beep! I couldn't understand your reply! Try the **!invite** command again!")
                else:
                    await Clembot.send_message(ctx.message.channel, "Beep Beep! No EX Raids have been reported in this server! Use **!exraid** to report one!")
            else:
                await Clembot.send_message(ctx.message.channel, "Beep Beep! That doesn't look like an EX Raid invitation to me! If it is, please message an admin to get added to the EX Raid channel manually!")
        else:
            await Clembot.send_message(ctx.message.channel, "Beep Beep! Your attachment was not a supported image format!")
    else:
        await Clembot.send_message(ctx.message.channel, "Beep Beep! Please upload your screenshot directly to Discord!")

@Clembot.event
async def on_command_error(error, ctx):
    channel = ctx.message.channel
    if isinstance(error, commands.MissingRequiredArgument):
        await Clembot.send_cmd_help(ctx)
    elif isinstance(error, commands.BadArgument):
        await Clembot.send_cmd_help(ctx)
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        logger.exception(type(error).__name__, exc_info=error)

Clembot.run(config['bot_token'])
