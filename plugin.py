###
# Copyright (c) 2017, Mike Burns
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.world as world
import supybot.ircutils as ircutils
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.schedule as schedule
import supybot.registry as registry
import requests
from ast import literal_eval
from trello import TrelloApi
import sys
import time
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('TrelloMon')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class TrelloMon(callbacks.Plugin):
    """Trello List Monitor bot"""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(TrelloMon, self)
        self.__parent.__init__(irc)
        self.trello = None
        self.reload_trello()
        self.last_run = {}
        self.DFG_id = None
        self.RCA_id = None
        self.DFG = []
        self.RCA = []
        for name in self.registryValue('lists'):
            self.register_list(name)
        try:
            schedule.addPeriodicEvent(self.check_trello, 30,
                                      name=self.name(), now=False)
        except:
            pass
        reload(sys)

    def debug(self, msg):
        self.log.debug(str(msg))

    def die(self):
        self.debug(self.name())
        self.__parent.die()
        schedule.removeEvent(self.name())

    def _send(self, message, channel, irc):
        '''send message to irc'''
        msg = ircmsgs.privmsg(channel, message)
        irc.queueMsg(msg)

    def reload_trello(self):
        self.trello = None
        self.trello = TrelloApi(self.registryValue('trelloApi'))
        self.trello.set_token(self.registryValue('trelloToken'))

    def reload(self, irc, msg, args):
        '''reload trello api'''
        self.reload_trello()
        if self.trello is not None:
            irc.replySuccess()
        else:
            irc.replyFailure()
    reloadtrello = wrap(reload, [])

    def kill(self, irc, msg, args):
        ''' kill auto-updates'''
        self.die()
    killagent = wrap(kill, ['admin'])

    def startagent(self, irc, msg, args):
        '''start the monitoring agent'''
        self.debug(self.name())
        try:
            self.die()
        except:
            pass
        schedule.addPeriodicEvent(self.check_trello, 20,
                                  name=self.name(), now=True)
    startagent = wrap(startagent, ['admin'])

    def apikey(self, irc, msg, args):
        '''print apikey'''
        irc.reply(self.registryValue('trelloApi'))
    apikey = wrap(apikey, [])

    def register_list(self, name, trelloid=""):
        install = conf.registerGroup(conf.supybot.plugins.TrelloMon.lists,
                                     name.lower())

        conf.registerChannelValue(install, "AlertMessage",
                                  registry.String("", """Prefix for all alerts for this trello list"""))

        conf.registerGlobalValue(install, "list_id",
                                 registry.String(trelloid, """the trello id for the list being monitored"""))

        conf.registerChannelValue(install, "interval",
                                  registry.PositiveInteger(10, """The cadence for polling the board"""))

        conf.registerChannelValue(install, "verbose", registry.Boolean(True,
                                  """Should this list report a summary or all cards"""))

        conf.registerChannelValue(install, "active", registry.Boolean(False,
                                  """Should this list be reported on this channel"""))

        conf.registerGlobalValue(install, "url",
                                 registry.String("https://trello.com", """link quick hash to the board containing
                                 this list"""))
        if trelloid == "":
            trelloid = self.registryValue("lists."+name+".list_id")
        if self.trello is not None:
            url = "https://trello.com/b/" + self.trello.lists.get_board(trelloid)['shortLink']
            self.setRegistryValue("lists."+name+".url", url)

    def get_custom_field_details(self, listid):
        '''get the custom field details'''
        # get url from the list
        self.debug("listid is " + str(listid))
        baseurl = "https://api.trello.com/1/boards/"
        # hard coded to get organizational plugin data
        querystring = {'lists': 'open', 'actions': 'all', 'members': 'none', 'card_pluginData': 'false', 'membersInvited': 'none', 'fields': 'name, desc, descData, closed, idOrganization, pinned, url, shortUrl, prefs, labelNames', 'organization_pluginData': 'true', 'memberships': 'none', 'pluginData': 'true', 'boardStars': 'none', 'cards': 'none', 'checklists': 'none', 'membersInvited_fields': 'all'}
        auth_opts = {'key': self.registryValue('trelloApi'),
                     'token': self.registryValue('trelloToken')}
        options = querystring
        options.update(auth_opts)
        self.debug("Auth Options passed:  " + str(options))
        boardid = self.trello.lists.get(listid, fields='idBoard')['idBoard']
        self.debug("found this board id:  " + str(boardid))
        r = requests.get(baseurl + boardid, params=options)
        self.debug("status code returned:  " + str(r.status_code))
        # FIXME -- add logic to determine the right plugin entry
        plugin_data = literal_eval(r.json()['pluginData'][0]['value'])['fields']
        for field in plugin_data:
            if field['n'] == 'DFG':
                self.DFG = field['o']
                self.debug("DFG mapping:  " + str(self.DFG))
                self.DFG_id = field['id']
                self.debug("DFG field id:  " + self.DFG_id)
            elif field['n'] == 'RCA':
                self.RCA = field['o']
                self.debug("RCA mapping:  " + str(self.RCA))
                self.RCA_id = field['id']
                self.debug("RCA field id:  " + self.RCA_id)

    def get_card_custom_fields(self, card):
        baseurl = 'https://api.trello.com/1/cards/'
        auth_opts = {'key': self.registryValue('trelloApi'),
                     'token': self.registryValue('trelloToken')}
        r = requests.get(baseurl + card + '/pluginData', params=auth_opts)
        # FIXME -- add logic for multiple plugins
        card_DFG = None
        card_RCA = None
        info = literal_eval(r.json()[0]['value'])['fields']
        for dfg in self.DFG:
            if self.DFG_id not in info:
                break
            elif dfg['id'] == info[self.DFG_id]:
                card_DFG = dfg['value']
                break
        for rca in self.RCA:
            if self.RCA_id not in info:
                break
            elif rca['id'] == info[self.RCA_id]:
                card_RCA = rca['value']
                break
        self.debug("Card DFG:  " + str(card_DFG))
        self.debug("Card RCA:  " + str(card_RCA))
        return [card_DFG, card_RCA]

    def addlist(self, irc, msg, args, name, trelloid):
        '''<name> <trello_id>
        Adds a new list that can be monitored'''
        self.register_list(name, trelloid)
        lists = self.registryValue('lists')
        lists.append(name.lower())
        self.setRegistryValue('lists', lists)
        irc.replySuccess()
    addlist = wrap(addlist, ['admin',
                             'somethingwithoutspaces',
                             'somethingwithoutspaces'])

    def get_trello_cards(self, list=None, label=None):
        result = []
        if list is None or list == "":
            return result
        for card in self.trello.lists.get_card(list):
            if label is None:
                result.append([card['name'], card['shortLink']])
            else:
                for card_label in card['labels']:
                    if label == card_label['name']:
                        result.append([card['name'], card['shortLink']])
        return result

    def check_trello(self):
        '''based on plugin config, scan trello for cards in the specified lists'''
        # for each irc network in the bot
        for irc in world.ircs:
            # for each channel the bot is in
            for chan in irc.state.channels:
                self.debug(chan)
                # for each list in the definition
                for entry in self.registryValue('lists'):
                    self.debug(entry)
                    # if not active in that channel (default is false), then
                    # do nothing
                    path = 'lists.' + entry + "."
                    self.get_custom_field_details(self.registryValue('lists.' + entry +'.list_id'))
                    if not self.registryValue("lists."+entry+".active."+chan):
                        self.debug("not active in chan: " + chan)
                        continue
                    # if no last_run time set, then set it
                    if entry+"_"+chan not in self.last_run:
                        self.debug("no last run")
                        self.last_run[entry+"_"+chan] = time.mktime(time.gmtime())
                    # compare last run time to current time to interval
                    # if less than interval, next
                    elif (float(time.mktime(time.gmtime()) - self.last_run[entry+"_"+chan]) <
                          float(self.registryValue("lists."+entry+".interval."+chan) * 60)):
                        self.debug("last run too recent")
                        continue
                    # if greater than interval, update
                    self.debug("last run too old or no last run")
                    self.last_run[entry+"_"+chan] = time.mktime(time.gmtime())
                    results = self.get_trello_cards(self.registryValue('lists.'+entry+'.list_id'))
                    message = self.registryValue("lists."+entry+".AlertMessage."+chan)
                    if results == []:
                        if self.last_run[entry+"_"+chan+"_count"] != 0:
                            self._send(message + " ALL CLEAR!!!", chan, irc)
                        self.last_run[entry+"_"+chan+"_count"] = 0
                        self.debug("no results")
                        continue
                    # check verbose setting per channel -- defaults to false
                    # TODO add label logic
                    self.last_run[entry+"_"+chan+"_count"] = len(results)
                    if self.registryValue("lists."+entry+".verbose."+chan):
                        self.debug("verbose")
                        for card in results:
                            custom = self.get_card_custom_fields(card[1])
                            if custom[0] is None:
                                dfgmsg = "<DFG:Unset>"
                            else:
                                dfgmsg = "<DFG:" + custom[0] + ">"
                            if custom[1] is None:
                                rcamsg = "RCA:Unset"
                            else:
                                rcamsg = "RCA: " + custom[1]
                            self._send(message + " " + dfgmsg + " " + card[0] +
                                       " -- https://trello.com/c/" +
                                       card[1] + " " + rcamsg, chan, irc)
                    else:
                        self.debug("not verbose")
                        self._send(message + " " + str(len(results)) + ' cards in ' + entry + ' -- ' + self.registryValue('lists.'+entry+'.url'), chan, irc)

    def execute_wrapper(self, irc, msgs, args):
        '''admin test script for the monitor command'''
        self.check_trello()
    execute = wrap(execute_wrapper, ['admin'])

    def test(self, irc, msgs, args):
        '''test'''
        irc.reply(self.registryValue('lists.failingtest.interval'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rdmb'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rhos-delivery'))
    tester = wrap(test, [])


Class = TrelloMon


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
