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
            schedule.addPeriodicEvent(self.check_trello,
                                      self.registryValue('queryinterval'),
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
        schedule.addPeriodicEvent(self.check_trello,
                                  self.registryValue('queryinterval'),
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
                                  registry.PositiveInteger(10, """The cadence
                                  for reporting this list on channel"""))

        conf.registerChannelValue(install, "verbose", registry.Boolean(True,
                                  """Should this list report a summary or all cards"""))

        conf.registerChannelValue(install, "active", registry.Boolean(False,
                                  """Should this list be reported on this channel"""))

        conf.registerGlobalValue(install, "url",
                                 registry.String("https://trello.com", """link quick hash to the board containing
                                 this list"""))

        conf.registerChannelValue(install, "dfg", registry.String("", """comma
                                 separated list of dfgs to report on"""))

        conf.registerChannelValue(install, "labels", registry.String("",
                                  """comma separated list of labels to show"""))
        if trelloid == "":
            trelloid = self.registryValue("lists." + name + ".list_id")
        if self.trello is not None:
            url = "https://trello.com/b/" + self.trello.lists.get_board(trelloid)['shortLink']
            self.setRegistryValue("lists." + name + ".url", url)

    def get_custom_field_details(self, listid):
        '''get the custom field details'''
        # get url from the list
        self.debug("listid is " + str(listid))
        baseurl = "https://api.trello.com/1/boards/"
        auth_opts = {'key': self.registryValue('trelloApi'),
                     'token': self.registryValue('trelloToken')}
        self.debug("Auth Options passed:  " + str(auth_opts))
        boardid = self.trello.lists.get(listid, fields='idBoard')['idBoard']
        self.debug("found this board id:  " + str(boardid))
        r = requests.get(baseurl + boardid + '/customFields', params=auth_opts)
        self.debug("status code returned:  " + str(r.status_code))
        # FIXME -- add logic to determine the right plugin entry
        for field in r.json():
            if field['name'] == 'DFG':
                self.DFG = {}
                for dfg in field['options']:
                    self.DFG[dfg['id']] = dfg['value']['text']
                self.debug("DFG mapping:  " + str(self.DFG))
                self.DFG_id = field['id']
                self.debug("DFG field id:  " + self.DFG_id)
            elif field['name'] == 'RCA':
                self.RCA = {}
                for rca in field['options']:
                    self.RCA[rca['id']] = rca['value']['text']
                self.debug("RCA mapping:  " + str(self.RCA))
                self.RCA_id = field['id']
                self.debug("RCA field id:  " + self.RCA_id)
            elif field['name'] == 'Owner':
                self.owner_id = field['id']

    def get_card_custom_fields(self, card):
        baseurl = 'https://api.trello.com/1/cards/'
        auth_opts = {'key': self.registryValue('trelloApi'),
                     'token': self.registryValue('trelloToken'),
                     'customFieldItems': 'true'}
        r = requests.get(baseurl + card, params=auth_opts)
        # FIXME -- add logic for multiple plugins
        card_DFG = None
        card_RCA = None
        self.debug(str(r.json()))
        if r.json() is []:
            self.debug("no plugindata found for card:" + card)
            return [card_DFG, card_RCA]
        info = r.json()['customFieldItems']
        for cf in info:
            if cf['idCustomField'] == self.DFG_id:
                card_DFG = self.DFG[cf['idValue']]
                continue
            if cf['idCustomField'] == self.RCA_id:
                card_RCA = self.RCA[cf['idValue']]
                continue
        self.debug("Card DFG:  " + str(card_DFG))
        self.debug("Card RCA:  " + str(card_RCA))
        if card_DFG is None:
            card_DFG = 'Unset'
        if card_RCA is None:
            card_RCA = 'Unset'
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

    def get_trello_cards(self, list=None):
        result = []
        if list is None or list == "":
            return result
        cards = self.trello.lists.get_card(list, fields="name,shortLink")
        for card in cards:
            custom = self.get_card_custom_fields(card['shortLink'])
            card['DFG'] = custom[0]
            card['RCA'] = custom[1]
        return cards

    def check_labels(card_labels, valid_labels):
        names = [label['name'] for label in card_labels]
        for i in valid_labels:
            for label in names:
                if i in label:
                    return True
        return False

    def check_trello(self):
        '''based on plugin config, scan trello for cards in the specified lists'''
        # for each irc network in the bot
        self.debug("here1")
        for irc in world.ircs:
            # for each list in the definition
            for entry in self.registryValue('lists'):
                self.debug(entry)
                # collect custom field info
                self.get_custom_field_details(self.registryValue('lists.' + entry + '.list_id'))
                # Collect all the list info first
                results = self.get_trello_cards(self.registryValue('lists.' + entry + '.list_id'))
                # for each channel the bot is in
                for chan in irc.state.channels:
                    self.debug(chan)
                    self.debug("here2:  " + chan)

                    # if not active in that channel (default is false), then
                    # do nothing
                    if not self.registryValue("lists." + entry + ".active." + chan):
                        self.debug("not active in chan: " + chan)
                        continue
                    # if no last_run time set, then set it
                    if entry + "_" + chan not in self.last_run:
                        self.debug("no last run")
                        self.last_run[entry + "_" + chan] = time.mktime(time.gmtime())
                    # compare last run time to current time to interval
                    # if less than interval, next
                    elif (float(time.mktime(time.gmtime()) - self.last_run[entry + "_" + chan]) <
                          float(self.registryValue("lists." + entry + ".interval." + chan) * 60)):
                        self.debug("last run too recent")
                        continue
                    # if greater than interval, update
                    self.debug("last run too old or no last run")
                    self.last_run[entry + "_" + chan] = time.mktime(time.gmtime())

                    # Filter out some cards from the list only for this channel
                    chan_set = []
                    try:
                        active_dfgs = self.registryValue('lists.' + entry + '.dfg.' + chan).split(',')
                    except:
                        active_dfgs = []
                    try:
                        valid_labels = self.registryValue('lists.' + entry + '.labels.' + chan).split(',')
                    except:
                        valid_labels = []
                    self.debug('active_dfgs:  ' + str(active_dfgs))
                    self.debug('valid labels:  ' + str(valid_labels))

                    for card in results:
                        if active_dfgs != [] and card['DFG'] not in active_dfgs:
                            self.debug("skipping card['name'] due to active_dfg")
                            continue
                        if valid_labels != [] and not check_labels(card['labels'], valid_labels):
                            self.debug("skipping card['name'] due to valid_labels")
                            continue
                        chan_set.append(card)

                    message = self.registryValue("lists." + entry + ".AlertMessage." + chan)
                    if chan_set == []:
                        if entry + "_" + chan + "_count" in self.last_run and self.last_run[entry + "_" + chan + "_count"] != 0:
                            self._send(message + " ALL CLEAR!!!", chan, irc)
                        self.last_run[entry + "_" + chan + "_count"] = 0
                        self.debug("no results")
                        continue
                    # check verbose setting per channel -- defaults to false
                    self.last_run[entry + "_" + chan + "_count"] = len(chan_set)
                    if self.registryValue("lists." + entry + ".verbose." + chan):
                        self.debug("verbose")
                        for card in chan_set:
                            dfgmsg = "<DFG:" + card['DFG'] + ">"
                            rcamsg = "RCA: " + card['RCA']
                            if self.registryValue('showlabels', chan):
                                if len(card['labels']) == 0:
                                    labelmsg = "  Labels:  None"
                                else:
                                    labellist = []
                                    for label in card['labels']:
                                        labellist.append(label['name'])
                                    labelmsg = "  Labels: " + ",".join(labellist)
                            else:
                                labelmsg = ""

                            if active_dfgs is None or active_dfgs == [''] or custom[0] in active_dfgs:
                                self._send(message + " " + dfgmsg + " " + card[0]
                                           + " -- https://trello.com/c/"
                                           + card[1] + " " + rcamsg + labelmsg, chan, irc)
                    else:
                        self.debug("not verbose")
                        self._send(message + " " + str(len(chan_set)) + ' cards in ' + entry + ' -- ' + self.registryValue('lists.' + entry + '.url'), chan, irc)

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
