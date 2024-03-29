import cgi
import os
import urllib2
import logging
import feedparser
import time
import socket

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api.urlfetch import DownloadError 

import gdata.calendar.service
import gdata.service
import atom.service
import gdata.calendar
import atom

nr_days = [31, 28, 31,30,31,30,31, 31, 30, 31, 30, 31]
day_s = 24*3600
year_s = 365*3600*24

class myMail(db.Model):
	mail_from = db.StringProperty(multiline=True)
	subject = db.StringProperty(multiline=True)
	content = db.StringProperty(multiline=True)
	date = db.IntegerProperty()

class myLastRecentTime(db.Model):
	myTime = db.IntegerProperty()
	
class ReadEmails(webapp.RequestHandler):
	def loginToCalendar(self, user, passwd):
		calendar_service = gdata.calendar.service.CalendarService()
		calendar_service.email = user
		calendar_service.password = passwd
		calendar_service.source = 'My mail to sms calendar'
	
		try:
			calendar_service.ProgrammaticLogin()
		except gdata.service.BadAuthentication, e:
			logging.error('Authentication error logging in: %s', e)
			return
		except Exception, e:
			logging.error('Error Logging in: %s', e)
			return
		logging.info('Successfully logged into calendar')
		return calendar_service
			
	def InsertSingleEvent(self, calendar_service, calendar, title='{Subiect}', 
                      content='{Content}', where='{Where}', 
                      start_time=None, end_time=None):
		event = gdata.calendar.CalendarEventEntry()
		event.title = atom.Title(text=title)
		event.content = atom.Content(text=content)
		event.where.append(gdata.calendar.Where(value_string=where))

		alternateLink = calendar.GetAlternateLink()
		if start_time is None:
			''' Use current time for the start_time and have the event last 1 minute '''
			start_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time() + 60*2))
			end_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time() + 60*3))
		event.when.append(gdata.calendar.When(start_time=start_time, end_time=end_time))
		for a_when in event.when: 
			if len(a_when.reminder) > 0: 
				a_when.reminder[0].minutes = 0
			else: 
				a_when.reminder.append(gdata.calendar.Reminder(minutes=0)) 
		'''Work-around 302 redirect error'''
		j = 3 
		while True: 
			if j < 1: 
				logging.error('Unable to post Google event %s ', title) 
				return 0 
			try: 
				new_event = calendar_service.InsertEvent(event, alternateLink.href)		
			except gdata.service.RequestError, inst: 
				thing = inst[0] 
				if thing['status'] == 302: 
					logging.warning('Received redirect - retrying %s ', title)
					j = j - 1 
					#time.sleep(2.0) 
					continue 
			except: 
				''' Some other exception '''
				raise 
			break
		return 1
			
	def get_unread_msgs(self, user, passwd):
		auth_handler = urllib2.HTTPBasicAuthHandler()
		auth_handler.add_password(
			realm='New mail feed',
			uri='https://mail.google.com',
			user='%s@gmail.com' % user,
			passwd=passwd
		)
		opener = urllib2.build_opener(auth_handler)
		urllib2.install_opener(opener)		

		try:
			feed = urllib2.urlopen('https://mail.google.com/mail/feed/atom')
		except urllib2.HTTPError, e:
			logging.error('The server couldn\'t fulfill the request.')
			logging.error('Error code: %s ', e.code)
			exit(1)
		except urllib2.URLError, e:
			logging.error('We failed to reach a server.')
			logging.error('Reason: %s .', e.reason)
			exit(2)
		except DownloadError, e:
			logging.error('Download error: %s.', e)
			exit(3)
		except Exception, e:
			logging.error('Other exception in urlopen: %s', e)
			exit(4)
			
		logging.info('Feed opened')
		return feed.read()
	
	def read_mail(self, feed, user, passwd):
		'''Parse the Atom feed and print a summary'''
		atom = feedparser.parse(feed)
		
		num_email = len(atom.entries)

		'''Get the time of last added message in db'''
		mostRecentTime = 0		
		my_times = db.GqlQuery("SELECT * FROM myLastRecentTime")
		if my_times.count() == 0:
			''' No dates in db. Add one'''
			currentTime = myLastRecentTime()
			currentTime.myTime = mostRecentTime		
			currentTime.put()
			return
		else:
			'''can contain 0 or 1 data maximum'''
			for my_time in my_times:
				mostRecentTime = my_time.myTime
		
		foundMoreRecent = 0
		
		for i in reversed(range(num_email)):
			mail = atom.entries[i]
			
			''' Get the date of the most recent message'''
			y = (int)(mail.modified.split('-')[0])
			m = (int)(mail.modified.split('-')[1])
			d = (int)(mail.modified.split('-')[2].split('T')[0])
			h = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[0])
			mi = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[1])
			sec = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[2].split('Z')[0])
			total = sec+mi*60+h*3600+(d-1)*day_s+sum(nr_days[0:(m-1)])*day_s+(y-2010)*year_s
			if (total > mostRecentTime) :				
				email = myMail()
				email.mail_from = "{"+(mail.author.partition('(')[0]).encode("ascii", "ignore")+"}"
				email.subject = "{"+mail.title.encode("ascii", "ignore")+"}"
				email.content = "{"+mail.summary.encode("ascii", "ignore")+"}"
				email.date = total
												
				'''Add SMS in calendar'''
				my_calendar_service = self.loginToCalendar(user, passwd) 
				''' Find myMail2sms calendar'''
				try:
					'''Get the CalendarListFeed'''
					all_calendars_feed = my_calendar_service.GetOwnCalendarsFeed()
				except Exception, e:
					logging.error('Error getting all calendars feed: %s.', e)
					return
	    
				'''Now loop through all of the CalendarListEntry items.'''
				for (index, cal) in enumerate(all_calendars_feed.entry):
					if (cal.title.text=="myMail2sms"):
						'''Add new event'''
						ok = self.InsertSingleEvent(my_calendar_service, cal, 
							email.mail_from+email.subject, "Yet another event",
							email.content)
						'''Put new unread email in db only if added succesfully to calendar'''
						if (ok == 1) :
							email.put()
							'''Message is more recent. Has to be added.'''
							mostRecentTime = total
							foundMoreRecent = 1
		
		if (foundMoreRecent == 1) :
			'''Update most recent time'''
			for my_time in my_times:
				my_time.delete()
				currentTime = myLastRecentTime()
				currentTime.myTime = mostRecentTime		
				currentTime.put()
			
	def get(self):
		user = "liviu22"
		passwd = "XXXXX"
		feed = self.get_unread_msgs(user, passwd)
		self.read_mail(feed, user, passwd)
			
		
application = webapp.WSGIApplication([('/check_inbox', ReadEmails)],
                                     debug=True)

def main():
	level = logging.WARNING
	logging.getLogger().setLevel(level)
	run_wsgi_app(application)

if __name__ == "__main__":
    main()
