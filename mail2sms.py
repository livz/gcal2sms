import cgi
import os
import urllib2
import feedparser

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class Greeting(db.Model):
    author = db.UserProperty()
    content = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)

class MainPage(webapp.RequestHandler):
    def get(self):
        greetings_query = Greeting.all().order('-date')
        greetings = greetings_query.fetch(10)

        if users.get_current_user():
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
        else:
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'

        template_values = {
            'greetings': greetings,
            'url': url,
            'url_linktext': url_linktext,
            }

        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))
		
class Guestbook(webapp.RequestHandler):
    def post(self):
        greeting = Greeting()

        if users.get_current_user():
            greeting.author = users.get_current_user()

        greeting.content = self.request.get('content')
        greeting.put()
        self.redirect('/')

class ClearLogs(webapp.RequestHandler):
	def post(self):
		#empty log database
		greetings = db.GqlQuery("SELECT * FROM Greeting")
		for greeting in greetings:
			greeting.delete()
			
		#redirect
		self.redirect('/')

class ReadEmails(webapp.RequestHandler):
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
	
	def read_mail(self, feed):
		'''Parse the Atom feed and print a summary'''
		atom = feedparser.parse(feed)
		
		num_email = len(atom.entries)

		if num_email > 1:
			print '%s new emails\n' % (len(atom.entries))
		else:
			print 'No new emails\n'
		for i in range(min(num_email,8)):
			mail = atom.entries[i]
			print '%d. %s' % (i+1, mail.title)
			print '%s' % (mail.summary.encode("iso-8859-15", "replace"))
			print '%s' % (mail.author.encode("iso-8859-15", "replace"))
			print '%s\n' % (mail.modified)
			
	def post(self):
		feed = self.get_unread_msgs("liviu22", "guardianangelDMX")
		self.read_mail(feed)
			
		#redirect
		self.redirect('/')
		
application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/sign', Guestbook),
                                      ('/clear_db', ClearLogs),
									  ('/read_emails', ReadEmails)],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()