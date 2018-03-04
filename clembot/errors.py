
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandError
from inspect import signature, getfullargspec

class TeamSetCheckFail(CommandError):
    'Exception raised checks.teamset fails'
    pass

class WantSetCheckFail(CommandError):
    'Exception raised checks.wantset fails'
    pass

class WildSetCheckFail(CommandError):
    'Exception raised checks.wildset fails'
    pass

class RaidSetCheckFail(CommandError):
    'Exception raised checks.raidset fails'
    pass

class CityChannelCheckFail(CommandError):
    'Exception raised checks.citychannel fails'
    pass

class WantChannelCheckFail(CommandError):
    'Exception raised checks.wantchannel fails'
    pass

class RaidChannelCheckFail(CommandError):
    'Exception raised checks.raidchannel fails'
    pass

class EggChannelCheckFail(CommandError):
    'Exception raised checks.raidchannel fails'
    pass

class NonRaidChannelCheckFail(CommandError):
    'Exception raised checks.nonraidchannel fails'
    pass

class ActiveRaidChannelCheckFail(CommandError):
    'Exception raised checks.activeraidchannel fails'
    pass

class CityRaidChannelCheckFail(CommandError):
    'Exception raised checks.cityraidchannel fails'
    pass

class RegionEggChannelCheckFail(CommandError):
    'Exception raised checks.cityeggchannel fails'
    pass

class RegionExRaidChannelCheckFail(CommandError):
    'Exception raised checks.cityeggchannel fails'
    pass

class ExRaidChannelCheckFail(CommandError):
    'Exception raised checks.cityeggchannel fails'
    pass

def missing_arg_msg(ctx):
    prefix = ctx.prefix.replace(ctx.bot.user.mention, '@' + ctx.bot.user.name)
    command = ctx.invoked_with
    callback = ctx.command.callback
    sig = list(signature(callback).parameters.keys())
    (args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations) = getfullargspec(callback)
    rq_args = []
    nr_args = []
    if defaults:
        rqargs = args[:(- len(defaults))]
    else:
        rqargs = args
    if varargs:
        if varargs != 'args':
            rqargs.append(varargs)
    arg_num = len(ctx.args) - 1
    sig.remove('ctx')
    args_missing = sig[arg_num:]
    msg = "Beep Beep! I'm missing some details! Usage: {prefix}{command}".format(prefix=prefix, command=command)
    for a in sig:
        if kwonlydefaults:
            if a in kwonlydefaults.keys():
                msg += ' [{0}]'.format(a)
                continue
        if a in args_missing:
            msg += ' **<{0}>**'.format(a)
        else:
            msg += ' <{0}>'.format(a)
    return msg

def custom_error_handling(bot, logger):

    @bot.event
    async def on_command_error(ctx, error):
        channel = ctx.channel
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.channel.send(missing_arg_msg(ctx))
        elif isinstance(error, commands.BadArgument):
            pages = bot.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await ctx.channel.send(page)
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, TeamSetCheckFail):
            msg = 'Beep Beep! Team Management is not enabled on this server. **!{cmd_name}** is unable to be used.'.format(cmd_name=ctx.command.name)
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, WantSetCheckFail):
            msg = 'Beep Beep! Pokemon Management is not enabled on this server. **!{cmd_name}** is unable to be used.'.format(cmd_name=ctx.command.name)
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, WildSetCheckFail):
            msg = 'Beep Beep! Wild Reporting is not enabled on this server. **!{cmd_name}** is unable to be used.'.format(cmd_name=ctx.command.name)
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, RaidSetCheckFail):
            msg = 'Beep Beep! Raid Management is not enabled on this server. **!{cmd_name}** is unable to be used.'.format(cmd_name=ctx.command.name)
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, CityChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'a Region report channel.'
            else:
                msg += 'one of the following region channels:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, WantChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in the following channel'.format(cmd_name=ctx.command.name)
            want_channels = bot.guild_dict[guild.id]['want_channel_list']
            if len(want_channels) > 1:
                msg += 's:\n'
            else:
                msg += ': '
            counter = 0
            for c in want_channels:
                channel = discord.utils.get(guild.channels, id=c)
                if counter > 0:
                    msg += '\n'
                msg += channel.mention
                counter += 1
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, RaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in a Raid channel. Use **!list** in any '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'Region report channel to see active raids.'
            else:
                msg += 'of the following Region channels to see active raids:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, RaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in an Egg channel. Use **!list** in any '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'Region report channel to see active raids.'
            else:
                msg += 'of the following Region channels to see active raids:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, NonRaidChannelCheckFail):
            msg = "Beep Beep! **!{cmd_name}** can't be used in a Raid channel.".format(cmd_name=ctx.command.name)
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, ActiveRaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in an Active Raid channel. Use **!list** in any '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'Region report channel to see active raids.'
            else:
                msg += 'of the following Region channels to see active raids:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, CityRaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in either a Raid channel or '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'a Region report channel.'
            else:
                msg += 'one of the following region channels:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, RegionEggChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in either a Raid Egg channel or '.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'a Region report channel.'
            else:
                msg += 'one of the following region channels:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, RegionExRaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in either a EX Raid channel or one of the following region channels:'.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'a Region report channel.'
            else:
                msg += 'one of the following region channels:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        elif isinstance(error, ExRaidChannelCheckFail):
            guild = ctx.guild
            msg = 'Beep Beep! Please use **!{cmd_name}** in a EX Raid channel. Use **!list** in any of the following region channels to see active raids:'.format(cmd_name=ctx.command.name)
            city_channels = bot.guild_dict[guild.id]['city_channels']
            if len(city_channels) > 10:
                msg += 'a Region report channel.'
            else:
                msg += 'one of the following region channels:'
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, name=c)
                    msg += '\n' + channel.mention
            await ctx.channel.send(msg)
            pass
        else:
            logger.exception(type(error).__name__, exc_info=error)
