import time_util
import re

class ArgParser:


    def pokemon_validator_mock(text):
        if text in ['kyogre', 'groudon', 'rayquaza', 'magikarp']:
            return True
        return False;

    def egg_validator_mock(text):
        if text in ['1', '2', '3', '4', '5']:
            return True
        return False;

    def eta_validator_mock(time_as_text, require_am_pm=True):
        return time_util.convert_into_time(time_as_text, require_am_pm)

    def translate_team(text):
        if text.lower() == 'm' or 'mystic' or 'blue':
            return 'mystic'

        if text.lower() == 'i' or 'instinct' or 'yellow':
            return 'instinct'

        if text.lower() == 'r' or 'valor' or 'red':
            return 'red'

        return None

    def gym_validator_mock(gym_code, message):

        gym_codes = ['stem', 'clco', 'mesc']
        gym_info = {}
        if gym_code in gym_codes:
            gym_info['gym_info'] = gym_code
            return gym_info
        return None

    def discord_username_mock(username):
        if re.match(r'@(.*)\#\d{4}', username):
            return True
        else:
            return re.match(r'(#\d{18})*', username)

    def extract_link_from_text(text):
        text = str(text)
        newloc = None
        mapsindex = text.find("/maps")
        newlocindex = text.rfind("http", 0, mapsindex)

        if newlocindex == -1:
            return newloc
        newlocend = text.find(" ", newlocindex)
        if newlocend == -1:
            newloc = text[newlocindex:]
        else:
            newloc = text[newlocindex:newlocend + 1]

        return newloc

    @classmethod
    def parse_arguments(self, text, list_of_options, options_methods={}, options_method_optional_parameters={}):
        response = {}

        args = text.split()

        response['length'] = len(args)

        command = args[0]
        del args[0]

        pokemon_method = options_methods.get('pokemon', ArgParser.pokemon_validator_mock)
        gym_lookup_method = options_methods.get('gym_info', ArgParser.gym_validator_mock)
        eta_method = options_methods.get('eta', ArgParser.eta_validator_mock)
        link_method = options_method_optional_parameters.get('link', ArgParser.extract_link_from_text)

        gym_lookup_message = options_method_optional_parameters.get('message', None)

        for option in list_of_options:
            # first check for command
            if option == 'command':
                response['command'] = command
            # identify pokemons
            elif option == 'pokemon':
                for arg in list(args):
                    if pokemon_method(arg):
                        poke_list = response.get('pokemon', [])
                        poke_list.append(arg)
                        response['pokemon'] = poke_list
                        args.remove(arg)
            elif option == 'subcommand':
                for arg in list(args):
                    if arg == 'assume':
                        response['subcommand'] = 'assume'
                        args.remove(arg)
                        break
            # identify egg level is specified
            elif option == 'egg':
                for arg in list(args):
                    if arg.isdigit():
                        if response.get('egg', None) == None:
                            response['egg'] = int(arg)
                            args.remove(arg)
                        else:
                            break

            # identify egg level is specified
            elif option == 'count':
                for arg in list(args):
                    if arg.isdigit():
                        if response.get('count', None) == None:
                            response['count'] = int(arg)
                            args.remove(arg)
                        else:
                            break
            # identify gym_code
            elif option == 'gym_info':
                for arg in list(args):
                    try:
                        gym_info = gym_lookup_method(arg, message=gym_lookup_message)
                        if gym_info:
                            response['gym_info'] = gym_info
                            args.remove(arg)
                    except Exception as error:
                        print(error)
                        pass
            # identify discord username
            elif option == 'mentions':
                for arg in list(args):
                    try:
                        if discord_username_mock(arg):
                            mention_list = response.get('mentions', [])
                            mention_list.append(arg)
                            response['mentions'] = mention_list
                            args.remove(arg)
                    except Exception as error:
                        print(error)
                        pass
            # identify partysize or index
            elif option == 'partysize' or option == 'index':
                for arg in list(args):
                    if arg.isdigit():
                        response[option] = int(arg)
                        args.remove(arg)
            # identify timer as the last number
            elif option == 'timer':
                for arg in list(args):
                    if arg.isdigit():
                        existig_timer = response.get(option, None)
                        if existig_timer:
                            args.append(existig_timer)
                        response[option] = int(arg)
                        args.remove(arg)

            # identify eta as valid time
            elif option == 'eta':
                for arg in list(args):
                    eta = eta_method(arg)
                    if eta:
                        response['eta'] = eta
                        args.remove(arg)
            elif option == 'link':
                for arg in list(args):
                    link = link_method(arg)
                    if link:
                        response['link'] = link
                        args.remove(arg)
        # all remaining arguments in others
        for arg in list(args):
            other_list = response.get('others', [])
            other_list.append(arg)
            response['others'] = other_list
            args.remove(arg)

        return response

def setup(bot):
    bot.add_cog(ArgParser(bot))





#
# def parse_test(text, format, options_method={}):
#     response = parse_arguments(text, format, options_method)
#     print("{text} = {response}\n".format(text=text, response=response))
#
#     return response
#
#     # print(response.get('others',None))
#
# def test():
#     parse_test("!raidegg 7 clco 3", ['command', 'egg', 'gym_info', 'timer', 'location'])
#
#     parse_test("!raidegg 5 clco 2", ['command', 'egg', 'gym_info', 'timer', 'location'])
#
#
#     parse_test("!add groudon clco 2:45pm", ['command', 'pokemon', 'gym_info', 'eta'], {'pokemon' : pokemon_validator_mock, 'eta' : time_util.convert_into_time})
#
#     parse_test("!raid groudon", ['command', 'pokemon', 'gym_info', 'timer', 'location'], {'pokemon': pokemon_validator_mock})
#
#     parse_test("!raid gkroudon art mural 2 23", ['command', 'pokemon', 'gym_info', 'timer', 'location'], {'pokemon' : pokemon_validator_mock})
#
#     parse_test("!c 2 groudon kyogre", ['command', 'pokemon', 'gym_info', 'partysize', 'location'])
#
#     parse_test("!raidegg 6 clco 5", ['command', 'egg', 'gym_info', 'timer', 'location'])
#
#     parse_test("!raid groudon clco 23", ['command', 'pokemon', 'gym_info', 'timer', 'location'])
#
#     parse_test("!c 6 m2 v3 groudon kyogre", ['command', 'pokemon', 'gym_info', 'partysize', 'location'])
#
#
#     parse_test("!update 3 groudon clco 3:00pm", ['command', 'index' ,'pokemon', 'gym_info', 'eta'])
#
#     parse_test("!update 3 groudon", ['command', 'index' ,'pokemon', 'gym_info', 'eta'], {'pokemon' : pokemon_validator_mock, 'eta' : eta_validator_mock})
#
#
# def test1():
#     parse_test("!raidegg 1 clco 0", ['command', 'egg', 'gym_info', 'timer', 'location'])
#
#     parse_test("!raid assume groudon", ['command', 'subcommand', 'pokemon'])
#
#
#
#
#
# def test2():
#     parameters = parse_test("!raidegg 5 gewa43 38", ['command', 'egg', 'gym_info', 'timer', 'location'],{'pokemon' : pokemon_validator_mock, 'link' : extract_link_from_text })
#     print(" ".join(str(x) for x in parameters.get('others')))
#
#     parse_test("!nest Squirtle Tonga Park ( some city ) https://goo.gl/maps/suEo9zDBCCP2", ['command','pokemon','link'])
#
#     parse_test("!exraid mesc", ['command', 'gym_info'])
#
#
# # ---------------uncomment this line to test stand alone-------------------------
#
# def test3():
#
#     if re.match(r'@(.*)\#\d{4}', '@G. (๑˃̵ᴗ˂̵)و-☆z#3529'):
#         print('matched')
#
#     print(re.match(r'@(.*)\#\d{4}', '@G. (๑˃̵ᴗ˂̵)و-☆z#3529'))
#     parse_test("!raidegg 5 600 Corp Pointe 13", ['command', 'egg', 'pokemon' , 'gym_info', 'timer', 'location' , 'link'])
#
#     parse_test("!c 3 @Bronzor#0409 2 @MEE6#4876 where are you", ['command', 'count', 'mentions'])
#
#     parse_test("!c", ['command', 'count'] )
#
#     parse_test("!c 5", ['command', 'count'] )
#
#     parse_test("!c @G. (๑˃̵ᴗ˂̵)و-☆z#3529  @B!#2022 4 @Bronzor#0409 @MEE6#4876", ['command', 'count', 'mentions'] )
#
#
#
# def main():
#     try:
#         test3()
#         print("main() finished")
#     except Exception as error:
#         print(error)
#     return
#
# main()