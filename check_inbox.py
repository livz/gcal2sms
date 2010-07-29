import cgi
import os
import urllib2
import feedparser
import time

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

import gdata.calendar.service
import gdata.service
import atom.service
import gdata.calendar
import atom

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
			print "Authentication error logging in: %s" % e
			return
		except Exception, e:
			print "Error Logging in: %s" % e
			return
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
			# Use current time for the start_time and have the event last 1 minute
			start_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time() + 60*2))
			end_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time() + 60*3))
		event.when.append(gdata.calendar.When(start_time=start_time, end_time=end_time))
		for a_when in event.when: 
			if len(a_when.reminder) > 0: 
				a_when.reminder[0].minutes = 0
			else: 
				a_when.reminder.append(gdata.calendar.Reminder(minutes=0)) 
		new_event = calendar_service.InsertEvent(event, alternateLink.href)		
	
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
		feed = urllib2.urlopen('https://mail.google.com/mail/feed/atom')
		return feed.read()
	
	def read_mail(self, feed, user, passwd):
		'''Parse the Atom feed and print a summary'''
		atom = feedparser.parse(feed)
		
		num_email = len(atom.entries)

		for i in range(num_email):
			mail = atom.entries[i]
			
			''' Get the date of the most recent message'''
			y = (int)(mail.modified.split('-')[0])
			m = (int)(mail.modified.split('-')[1])
			d = (int)(mail.modified.split('-')[2].split('T')[0])
			h = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[0])
			mi = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[1])
			sec = (int)(mail.modified.split('-')[2].split('T')[1].split(':')[2].split('Z')[0])
			total = sec+mi*60+h*3600+d*24*3600+(y-2010)*365*3600*24
			
			my_times = db.GqlQuery("SELECT * FROM myLastRecentTime")
			if my_times.count() == 0:
				''' No dates in db. Add one'''
				currentTime = myLastRecentTime()
				currentTime.myTime = total		
				currentTime.put()
			else:
				'''can contain o or 1 data maximum'''
				for my_time in my_times:
					if my_time.myTime < total :
						#New unread email 
						my_time.delete()
						currentTime = myLastRecentTime()
						currentTime.myTime = total		
						currentTime.put()
				
						'''If new unread mail, add to emails db'''
						email = myMail()
						email.mail_from = mail.author.encode("iso-8859-15", "replace")
						email.subject = mail.title
						email.content = mail.summary.encode("iso-8859-15", "replace")
						email.date = total
						email.put()
						
						'''Add SMS in calendar'''
						my_calendar_service = self.loginToCalendar(user, passwd) #login to Google Calendar
						''' Find myMail2sms calendar'''
						try:
						#Get the CalendarListFeed
							all_calendars_feed = my_calendar_service.GetOwnCalendarsFeed()
						except Exception, e:
							print "Error getting all calendar feed: %s" % (e)
							return
	    
						#Now loop through all of the CalendarListEntry items.
						for (index, cal) in enumerate(all_calendars_feed.entry):
							if (cal.title.text=="myMail2sms"):
								#Add new event
								self.InsertSingleEvent(my_calendar_service, cal, 
								email.mail_from+email.subject, "Yet another event",
								email.content)
								return
			
	def get(self):
		user = "liviu22"
		passwd = "guardianangelDMX"
		feed = self.get_unread_msgs(user, passwd)
		self.read_mail(feed, user, passwd)
			
		
application = webapp.WSGIApplication([('/check_inbox', ReadEmails)],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
