#!/usr/bin/python

import praw
import sys
import re
import time
import random
import urllib
import urllib2
import simplejson
import lxml.html
from lxml.cssselect import CSSSelector


def readConfig ():
    f = open('wayr.conf', 'r')
    buf = f.readlines()
    f.close()


    for b in buf:
        if b[0] == '#' or len(b) < 5:
            continue

        if b.startswith('username:'):
            USERNAME = b[len('username:'):].strip()

        if b.startswith('password:'):
            PASSWORD = b[len('password:'):].strip()

    if not USERNAME or not PASSWORD:
        print ("Missing param from conf file")
        quit()

    return USERNAME, PASSWORD




def init (useragent):
    r = praw.Reddit(user_agent=useragent)
    # so that reddit wont translate '>' into '&gt;'
    r.config.decode_html_entities = True
    return r


def login (r, username, password):
    Trying = True
    while Trying:
        try:
            r.login(username, password)
            print('Successfully logged in')
            Trying = False
        except praw.errors.InvalidUserPass:
            print('Wrong Username or Password')
            quit()
        except Exception as e:
            print("%s" % e)
            time.sleep(5)



def getBookImage(url, debug=[]):

    # Get an image from the provided goodreads.com url

    # use this url to search using ISBN
    # url = "http://www.goodreads.com/search/search?search_type=books&search%5Bquery%5D=" + isbn
    image = ""

    count = 0
    ok = False
    while not ok:
        try:
            usock = urllib2.urlopen(url)
            data = usock.read()
            usock.close()
            ok = True
        except Exception as e:
            count += 1
            if count >= 2:
                debug.append('Exception1 in getBookUrl(): %s ' % (e))
                print (debug[-1])
                return "", ""
            else:
                time.sleep(1)


    try:
        # get the 'coverImage'
        tree = lxml.html.fromstring(data)
        sel = CSSSelector('img#coverImage')
        css = sel(tree)
        image = css[0].get('src')

        # get the 'canonical' url - the real url of this webpage
        sel = CSSSelector('head link')
        css = sel(tree)
        for acss in css:
          if acss.get('rel') == 'canonical':
              url = acss.get('href')
              break

    except Exception as e:
        debug.append('Exception2 in getBookUrl(): url:%s -  %s ' % (url, e))
        print (debug[-1])
        return "", ""

    return url, image



def searchGoodreadsWithGoogle(title, author, debug=[]):

    # use google search engine to search goodreads for a title/author

    debug.append("searchGoodreads...(): ENTER " + title + author)
    grUrl = ""
    try:
        titleName = urllib.quote(title.encode('utf-8'))
        authorName = urllib.quote(author.encode('utf-8'))

        url = "https://ajax.googleapis.com/ajax/services/search/web?v=1.0&q=site%3agoodreads%2ecom%20%22" + titleName + "%22%20%22" + authorName + "%22"
        debug.append("searchGoodreads...(): google search url " + url)

        request = urllib2.Request(url, None, {'Referer': 'www.reddit.com'})
        response = urllib2.urlopen(request)
        results = simplejson.load(response)

        for x in results['responseData']['results']:
            # the correct url will have /book/show in it
            if "/book/show/" in x['url']:
                grUrl = x['url']
                break

    except Exception as e:
        debug.append('Exception in searchGoodreadsWithGoogle(): %s ' % (e))
        print(debug[-1])

    debug.append("searchGoodreads...(): google search results: " + grUrl)
    return grUrl





def saveToWikiPage(r, bookList, errors, threadTitle):
    print("saveToWikiPage() entered")

    # randomize (shuffle) the list
    random.shuffle(bookList)

    newWp = ""
    sr = r.get_subreddit("books")

    newWp = "### " + threadTitle + "\n\n"
    newWp += "---\n\nBook Count: %d\n\n---\n\n" % (len(bookList))

    for x in bookList:
        newWp += "#{Book} %s\n\n{author} %s\n\n{imageUrl} %s\n\n{bookUrl} %s\n\n{Blurb} %s\n\n{user} %s\n\n {comma} %s\n\n" % \
                    (x['title'], x['author'], x['imageUrl'], x['bookUrl'], x['redditUrl'], x['user'], x['commaNoBy'])

    newWp += "---\n\n### Errors\n\n"

    for x in errors:
        newWp += x + "\n\n"

    # save it to wiki/wayr-prep to be checked.  must be moved manually to wiki/wayr after verifing data
    sr.edit_wiki_page("wayr-prep", newWp)



def addToBookList(bookList, title, author, grUrl, imageUrl, redditUrl, user, commaNoBy):

    found = False
    for x in bookList:
        if x['imageUrl'] == imageUrl:
            print("\n>>>>>Found Dup:\n%s (%s)\n(%s)" % (title, redditUrl, x['redditUrl']))
            found = True
            break

    if not found:
        bookData = {'title': title, 'author': author, 'bookUrl': grUrl, 'imageUrl': imageUrl,
                    'redditUrl': redditUrl, 'user':"/u/"+user, 'commaNoBy':commaNoBy}
        bookList.append(bookData)

    return bookList





def getBooksFromComments (r, tid):

    bookList = []
    errors = []
    srchstr = "([^\*]{1,200}?)[\s*|,]by\s+([^\*]{1,100})"

    info = r.get_info(thing_id=tid)
    info.replace_more_comments()
    comments=info.comments

    print ("got comments, running...")
    ok = True
    count = 0

    print("scan: ***************** number of comments = %s" % len(comments))

    for c in comments:
        count += 1

        tags = re.findall("\*\*([^\*]{1,200})\*\*", c.body)

        if tags:
            for x in tags:
                # replace the crazy A0 char with space
                x = re.sub("\xa0", " ", x)
                print("\ngot tags")
                print(x.encode('utf-8'))

                # search for a string of text in between double asterisks (**the title, by the author**)
                x = re.sub("\(.*?\)", " ", x)

                # search for title and author separated by "by"
                res = re.search(srchstr, x, re.I)
                if not res:
                    # try searching without "by"
                    # find the last comma and split on that
                    index = x.rfind(",")
                    if index > 0:
                        t = x[:index]
                        a = x[index+1:]
                        commaNoBy = True
                    else:
                        # this one has no comma or "by" to separate the title/author so discard it
                        print ("NO GOOD1 --- " + x.encode('utf-8'))
                        errors.append("Bad Format1: " + x)
                        continue

                else:
                    t,a = res.group(1), res.group(2)
                    commaNoBy = False

                if not t or not a:
                    print ("blank tags in " + c.body)
                    continue
                if t.endswith(","):
                    t = t[:-1]
                if a.endswith("."):
                    a = a[:-1]

                print (t,a)

                # sleep for 10 seconds or else google complains for accessing it too fast
                time.sleep(10)
                imageUrl = ""
                grUrl = searchGoodreadsWithGoogle(t, a)
                if grUrl:
                    grUrl, imageUrl = getBookImage(grUrl)
                    if grUrl and imageUrl:
                        print("SUCCESS -- Got imageUrl.  Count = %d" % count)
                        bookList = addToBookList(bookList, t, a, grUrl, imageUrl, c.permalink, c.author.name, commaNoBy)

                if not imageUrl:
                    # search wasn't successful (mispelling?) or couldn't find an image
                    errors.append(t + " --- " + a + " --- " + grUrl)



    return bookList, errors




def getWeeklyThread (threadTitle):

    # get the 2nd most recent thread

    srch = r.search("flair:weeklythread title:\"what books are you reading\"", sort="new", subreddit="books", period="month")

    first = True
    for x in srch:
        if first:
            first = False
            continue
        return x.fullname, x.title

    return "",""


if __name__=='__main__':

    username, password = readConfig()
    r = init("/u/"+username+" wayr")
    r.login(username, password)

    tid, threadTitle = getWeeklyThread(r)
    if tid:
        print (threadTitle)
        bookList, errors = getBooksFromComments(r, tid)
        saveToWikiPage(r, bookList, errors, threadTitle)



