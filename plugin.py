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
import supybot.registry as registry
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
        self.last_run = []
        if self.trello is not None:
            self.running = True
        else:
            self.running = False
        for name in self.registryValue('lists'):
            self.register_list(name)
        reload(sys)

    def debug(self, msg):
        if self.registryValue('debug'):
            print "DEBUG:  msg"

    def _send(self, msg, channel, irc):
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
        else :
            irc.replyFailure()
    reloadtrello = wrap(reload, [])

    def isrunning(self, irc, msg, args):
        ''' show status of bot'''
        irc.reply(self.running)
    isrunning = wrap(isrunning, [])

    def run(self, irc, msg, args):
        ''' start the bot -- may take up to a minute to start getting results
        '''
        if self.trello is not None:
            self.running = True
            irc.replySuccess()
        else:
            self.running = false
            self.reply("""Trello API and token not correctly configured or trello
            unavailable""")
    run = wrap(run, [])

    def kill(self, irc, msg, args):
        ''' kill auto-updates'''
        self.running = False
        irc.replySuccess()
    kill = wrap(kill, [])

    def apikey(self, irc, msg, args):
        '''print apikey'''
        irc.reply(self.registryValue('trelloApi'))
    apikey = wrap(apikey, [])

    def register_list(self, name, trelloid=""):
        install = conf.registerGroup(conf.supybot.plugins.TrelloMon.lists,
        name.lower())

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
            url="https://trello.com/b/" + self.trello.lists.get_board(trelloid)['shortLink']
            self.setRegistryValue("lists."+name+".url", url)


    def addlist(self, irc, msg, args, name, trelloid):
        '''<name> <trello_id>
        Adds a new list that can be monitored'''
        self.register_list(name, trelloid)
        lists = self.registryValue('lists')
        lists.append(name.lower())
        self.setRegistryValue('lists',lists)
        irc.replySuccess()
    addlist = wrap(addlist, ['admin',
    'somethingwithoutspaces','somethingwithoutspaces'])

    def get_trello_cards(self, list=CRITICAL_LIST_ID, label=None):
        result=[]
        if list is Null or list == "":
            return result
        for card in self.trello.lists.get_card(list):
            if label is None:
                result.append(card['name'])
            else:
                for card_label in card['labels']:
                    if label == card_label['name']:
                        result.append(card['name'])
        return result

    def execute(self, irc, msgs, args):
        '''execute'''
        #while self.running:
        for j in [1]:
            #for each irc network in the bot
            for i in world.ircs:
                debug(i)
                #for each channel the bot is in
                for chan in i.state.channels:
                    debug(chan)
                    #for each list in the definition
                    for entry in self.registryValue('lists'):
                        debug(entry)
                        #if not active in that channel (default is false), then
                        # do nothing
                        if not self.registryValue(lists+"."+entry+".active."+chan):
                            debug("not active in chan: " + chan)
                            continue
                        #if no last_run time set, then set it
                        if lists+"_"+chan not in self.lastrun:
                            debug("no last run")
                            self.last_run[entry+"_"+chan] = time.mktime(time.gmtime())
                        #compare last run time to current time to interval
                        # if less than interval, next
                        elif (float(time.mktime(time.gmtime()) - self.last_run[entry+"_"+chan]) <
                            float(self.registryValue(lists+"."+entry+".interval."+chan)
                            * 60)):
                            debug("last run too recent")
                            continue
                        #if greater than interval, update
                        debug("last run too old or no last run")
                        results = self.get_trello_cards(entry)
                        if results == []:
                            debug("no results")
                            continue
                        # check verbose setting per channel -- defaults to false
                        message = self.registryValue(lists+"."+entry+"alertMessage")
                        if self.registryValue(lists+"."+entry+".verbose"):
                            for card in results:
                                self._send(message + card, chan, irc)
                        else:
                            self._send(message + len(results) + " card(s) in "
                                + list, chan, irc)
                        # TODO add label logic
            time.sleep(30)
    execute = wrap(execute, [])

    def test(self, irc, msgs, args):
        '''test'''
        irc.reply(self.registryValue('lists.failingtest.interval'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rdmb'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rhos-delivery'))
    tester = wrap(test, [])


Class = TrelloMon


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
