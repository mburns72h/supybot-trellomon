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
import re
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

        conf.registerChannelValue(install, "custom_field_filter", registry.String("", """comma
                                 separated list of dfgs to report on"""))

        conf.registerChannelValue(install, "precustom", registry.String("DFG: %DFG%",
                                  """Custom Field info to display prior to the
                                  card details and after the Alert Message"""))

        conf.registerChannelValue(install, "postcustom", registry.String("RCA: %RCA%",
                                  """Custom Field info to display after the
                                  card details and prior to labels (if
                                  enabled).  To show a field, please enter it
                                  as ${field_name}"""))

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
        return r.json()

    def get_card_custom_fields(self, card):
        baseurl = 'https://api.trello.com/1/cards/'
        auth_opts = {'key': self.registryValue('trelloApi'),
                     'token': self.registryValue('trelloToken'),
                     'customFieldItems': 'true'}
        r = requests.get(baseurl + card, params=auth_opts)
        return r.json()['customFieldItems']

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
        cards = self.trello.lists.get_card(list, fields="name,shortLink,shortUrl,labels")
        self.debug("found %d cards" % len(cards))
        for card in cards:
            card['customFieldItems'] = self.get_card_custom_fields(card['shortLink'])
        return cards

    def check_labels(self, card_labels, valid_labels):
        names = [label['name'] for label in card_labels]
        for i in valid_labels:
            for label in names:
                if i.upper() in label.upper():
                    return True
        return False

    def get_custom_field_value(self, field, custom_field_info):
        for cf in custom_field_info:
            if field['idCustomField'] == cf['id']:
                if cf['type'] == 'list':
                   for option in cf['options']:
                        if option['id'] == field['idValue']:
                            return str(option['value']['text'])
                elif cf['type'] == 'text':
                    return str(entry['value']['text'])
                elif cf['type'] == 'checkbox':
                    return str(field['value']['checked'])
        return None

    def _deref_custom(self, basestr, custom_info, card):
        ''' pass in the base string, custom field info and a card
        and handle replacing all the variables in basestr with the appropriate
        variables from the card'''
        p = re.compile(r'\${\w+}')
        self.debug("base message:  " + basestr)
        for match in p.finditer(basestr):
            #get the right substring without the ${} wrapper
            variable=match.group()[2:-1]
            self.debug("match:  " + str(variable))
            custom_field = None
            # get the custom field id
            for field in custom_info:
                self.debug("checking custom field:  " + field['name'])
                if field['name'] == variable:
                    custom_field = field
                    self.debug("found custom_field: " + field['name'])
                    break
            if custom_field is None:
                basestr = basestr.replace(match.group(), "N/A")
            else:
                for entry in card['customFieldItems']:
                    if entry['idCustomField'] == custom_field['id']:
                        value = self.get_custom_field_value(entry, custom_info)
                basestr = basestr.replace(match.group(), str(value))
        return basestr

    def check_custom_filter(self, card, custom_filter, custom_field_info):
        '''return true if this card should be filtered out'''
        if custom_filter is None or custom_filter == "":
            self.debug("custom filter not set")
            return False
        for criteria in value.split(','):
            (field_name, value) = criteria.split(':',1)
            self.debug('custom field filter on field "%s" with value "%s"' % (field, value))
            for cf in custom_field_info:
                if cf['name'] == field_name:
                    break
            for field in card['customFieldItems']:
                if field['idCustomField'] == cf['id']:
                    if value == get_custom_field_Value(field, custom_field_info):
                        return False
        return True

    def check_trello(self):
        '''based on plugin config, scan trello for cards in the specified lists'''
        # for each irc network in the bot
        self.debug("starting check_trello")
        for irc in world.ircs:
            # for each list in the definition
            for entry in self.registryValue('lists'):
                self.debug("list:  " + str(entry))
                # collect custom field info
                custom_fields = self.get_custom_field_details(self.registryValue('lists.' + entry + '.list_id'))
                # Collect all the list info first
                results = self.get_trello_cards(self.registryValue('lists.' + entry + '.list_id'))
                # for each channel the bot is in
                for chan in irc.state.channels:
                    self.debug("channel  " + str(chan))
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
                        valid_labels = self.registryValue('lists.' + entry + '.labels.' + chan).split(',')
                        for glabel in self.registryValue('labels', chan).split(','):
                            if glabel not in valid_labels:
                                valid_labels.append(glabel)
                    except:
                        valid_labels = []
                    if '' in valid_labels:
                        valid_labels.remove('')
                    self.debug('valid labels:  ' + str(valid_labels))

                    for card in results:
                        # filter by custom fields
                        if self.check_custom_filter(card, self.registryValue('lists.' + entry + '.custom_field_filter.' + chan), custom_fields):
                            self.debug("skipping %s due to custom field filter" % card['name'])
                            continue
                        if valid_labels != [] and not self.check_labels(card['labels'], valid_labels):
                            self.debug("skipping %s due to valid_labels" %
                                       card['name'])
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
                    self.debug("verbose is " + str(self.registryValue("lists." + entry + '.verbose.' + chan)))
                    if self.registryValue("lists." + entry + ".verbose." + chan):
                        self.debug("verbose")
                        for card in chan_set:
                            # Build the message in the format:  <Alert> <precustom> <details> <postcustom> <labels>
                            precustom = self._deref_custom(self.registryValue('lists.' + entry + '.precustom.' + chan), custom_fields, card)
                            postcustom = self._deref_custom(self.registryValue('lists.' + entry + '.postcustom.' + chan), custom_fields, card)
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

                            self._send(message + " " + precustom + " " +
                                       card['name'] + " -- " + card['shortUrl'] +
                                       " " + postcustom + labelmsg, chan, irc)
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
