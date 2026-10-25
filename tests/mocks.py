import time, json
from datetime import datetime, timedelta, timezone
now=datetime.now(timezone.utc)
iso=lambda d: (now-timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")
ep=lambda d: int((now-timedelta(days=d)).timestamp())
rfc=lambda d: (now-timedelta(days=d)).strftime("%a, %d %b %Y %H:%M:%S GMT")
def rpost(title,sub,author,days,text=""):
    return {"data":{"title":title,"selftext":text,"subreddit":sub,"author":author,"created_utc":ep(days),"permalink":f"/r/{sub}/comments/x{abs(hash(title))%99999}/"}}
R={
 "boards-api.greenhouse.io/v1/boards/gitlab/jobs":{"jobs":[
   {"title":"Senior Revenue Operations Analyst","location":{"name":"Remote, Worldwide"},"absolute_url":"https://job/gl1","updated_at":iso(5)},
   {"title":"Backend Engineer","location":{"name":"Remote"},"absolute_url":"https://job/gl2","updated_at":iso(3)}]},
 "api.lever.co/v0/postings/zapier":[{"text":"HubSpot Administrator","categories":{"location":"Remote - US"},"workplaceType":"remote","hostedUrl":"https://job/z1","createdAt":ep(10)*1000}],
 "apply.workable.com/api/v1/widget/accounts/acmedental":{"name":"Acme Dental","jobs":[{"title":"Front Desk & Admin Assistant","city":"Austin","country":"United States","telecommuting":False,"url":"https://job/ad1","published_on":iso(8)[:10]}]},
 "remoteok.com/api":[{"legal":"..."},
   {"company":"Brightpath Agency","position":"GoHighLevel Automation Specialist","location":"Worldwide","url":"https://remoteok.com/1","date":iso(2)},
   {"company":"Deel","position":"Customer Success Manager","location":"USA","url":"https://remoteok.com/2","date":iso(6)},
   {"company":"Somecorp","position":"Rust Engineer","location":"Worldwide","url":"https://remoteok.com/3","date":iso(1)}],
 "remotive.com/api/remote-jobs":{"jobs":[{"company_name":"Nimbus Realty","title":"Virtual Assistant (Data Entry & CRM)","candidate_required_location":"Worldwide","url":"https://remotive.com/1","publication_date":iso(4)}]},
 "himalayas.app/jobs/api":{"jobs":[{"companyName":"Close","title":"Account Executive","locationRestrictions":[],"applicationLink":"https://himalayas.app/1","pubDate":ep(12)}]},
 "/r/forhire/new.json":{"data":{"children":[
   rpost("[Hiring] GoHighLevel VA needed for our marketing agency - $15/hr","forhire","agencyowner22",3,"Need someone to manage pipelines and automations in GHL."),
   rpost("[For Hire] Experienced virtual assistant available","forhire","va_pro",1),
   rpost("[Hiring] Logo designer","forhire","x",2)]}},
 "/r/gohighlevel/new.json":{"data":{"children":[
   rpost("Looking for someone to build GHL snapshots and workflows for my roofing clients","gohighlevel","roofpro",9),
   rpost("How do I change my favicon?","gohighlevel","newbie",2)]}},
 "/r/smallbusiness/new.json":{"data":{"children":[
   rpost("Need a virtual assistant for data entry - where do I find one?","smallbusiness","bakery_mia",20),
   rpost("Old post: need a CRM","smallbusiness","old",120)]}},
 "/r/Entrepreneur/new.json":{"data":{"children":[
   rpost("Just launched my cleaning business 3 months ago - how do I get clients? Sales are slow","Entrepreneur","sparkle_clean",4),
   rpost("Motivational quote of the day","Entrepreneur","q",1)]}},
 "/r/sweatystartup/new.json":{"data":{"children":[
   rpost("Tracking leads in a spreadsheet and they keep falling through the cracks","sweatystartup","hvac_joe",7,"Small HVAC shop, 3 techs. Missed calls = lost jobs.")]}},
 "/r/Solopreneur/new.json":{"data":{"children":[
   rpost("Burnt out doing everything myself - is it time for my first hire?","Solopreneur","coach_amy",2)]}},
 "https://bloomflorist.com":"<html><link href='https://static1.squarespace.com/x.css'></html>",
 "reddit.com/search.json?q=%22Bloom%20Florist%22":{"data":{"children":[
   rpost("Bloom Florist owner here: we keep losing leads from Instagram DMs","smallbusiness","bloom_owner",10)]}},
 "reddit.com/search.json?q=%22Acme%20Dental%22":{"data":{"children":[
   rpost("Acme Dental is looking for a GoHighLevel expert to set up our booking workflows","dentistry","acme_mgr",6)]}},
 "hn.algolia.com/api/v1/search_by_date?query=virtual%20assistant":{"hits":[
   {"objectID":"111","comment_text":"Nimbus Realty | Virtual Assistant &amp; CRM data entry | REMOTE (Worldwide) | Full-time<p>We use HubSpot...","story_title":"Ask HN: Who is hiring? (October 2026)","author":"nimbus","created_at":iso(15)},
   {"objectID":"112","comment_text":"Freelancer | Virtual assistant | Remote | I offer admin help","story_title":"Ask HN: Freelancer? Seeking freelancer? (October 2026)","author":"me","created_at":iso(3)}]},
 "news.google.com/rss/search?q=%22Deel%22":"""<rss><channel><item><title>Deel hiring 200 customer success staff as it expands in Asia</title><link>https://news/1</link><pubDate>%s</pubDate></item>
 <item><title>Deel raises $300M Series E</title><link>https://news/2</link><pubDate>%s</pubDate></item></channel></rss>"""%(rfc(12),rfc(30)),
 "freelancer.com/api/projects/0.1/projects/active/?query=gohighlevel":{"status":"success","result":{"projects":[
   {"id":40778167,"owner_id":501,"title":"GoHighLevel Agency & Sub-Account Setup","seo_url":"go-high-level/GoHighLevel-Agency-Sub-Account-Setup","preview_description":"My agency runs on GoHighLevel and I need a specialist to set up pipelines","time_submitted":ep(2),"type":"hourly","currency":{"code":"USD"},"budget":{"minimum":10.0,"maximum":15.0},"bid_stats":{"bid_count":40}},
   {"id":40778168,"title":"Logo for bakery","seo_url":"logo/Logo-for-bakery","preview_description":"Need a cute logo","time_submitted":ep(1),"type":"fixed","currency":{"code":"USD"},"budget":{"minimum":30.0,"maximum":50.0},"bid_stats":{"bid_count":90}},
   {"id":40778169,"title":"Old GHL project","seo_url":"x/old","preview_description":"GoHighLevel funnels","time_submitted":ep(200),"type":"fixed","currency":{"code":"USD"},"budget":{"minimum":100.0,"maximum":200.0},"bid_stats":{"bid_count":5}}]}},
 "freelancer.com/api/projects/0.1/projects/active/?query=crm":{"status":"success","result":{"projects":[
   {"id":40778167,"owner_id":501,"title":"GoHighLevel Agency & Sub-Account Setup","seo_url":"go-high-level/GoHighLevel-Agency-Sub-Account-Setup","preview_description":"My agency runs on GoHighLevel and I need a specialist to set up pipelines","time_submitted":ep(2),"type":"hourly","currency":{"code":"USD"},"budget":{"minimum":10.0,"maximum":15.0},"bid_stats":{"bid_count":40}}]}},
 "freelancer.com/api/users/0.1/users":{"status":"success","result":{"users":{
   "501":{"id":501,"username":"roofpro","public_name":"Sam Roof","location":{"country":{"name":"United States"}}}}}},
 "news.google.com/rss/search?q=gohighlevel":"""<rss><channel>
  <item><title>Harbor Dental selects GoHighLevel for patient follow-ups - Health Daily</title>
   <link>https://news/hd1</link><pubDate>%s</pubDate></item>
  <item><title>Top 5 CRM trends to watch in 2026 - TechNews</title>
   <link>https://news/junk1</link><pubDate>%s</pubDate></item></channel></rss>"""%(rfc(4),rfc(2)),
 "news.google.com/rss/search?q=raises%20seed%20funding":"""<rss><channel>
  <item><title>Harbor Dental raises seed funding to open more clinics - Startup Wire</title>
   <link>https://news/hd2</link><pubDate>%s</pubDate></item></channel></rss>"""%rfc(6),
 "https://harbordental.com":"""<html><title>Harbor Dental - family dentistry</title>
  <script src='https://widgets.leadconnectorhq.com/loader.js'></script>
  <a href="mailto:amy.chen@harbordental.com">email us</a></html>""",
 "jobicy.com/api/v2/remote-jobs":{"jobs":[{"companyName":"Peak Roofing","jobTitle":"GoHighLevel Automation Specialist","jobGeo":"Anywhere","url":"https://jobicy.com/jobs/1","pubDate":iso(3)}]},
 "workingnomads.com/api/exposed_jobs":[{"company_name":"River Clinics","title":"Zoho CRM Administrator","location":"Worldwide","url":"https://wn/1","pub_date":iso(3)}],
 "austin.craigslist.org/search/ggg?format=rss&query=virtual%20assistant":"""<rss><channel>
  <item><title>Need virtual assistant 10 hrs/wk for my clinic</title>
   <link>https://austin.craigslist.org/ggg/123.html</link><pubDate>%s</pubDate>
   <description>Looking for a VA to handle inbox, scheduling and data entry.</description></item>
  <item><title>Selling my couch</title>
   <link>https://austin.craigslist.org/ggg/124.html</link><pubDate>%s</pubDate>
   <description>Good condition, pick up only.</description></item></channel></rss>"""%(rfc(2),rfc(2)),
 "https://acmedental.com":"<html><script src='https://widgets.leadconnectorhq.com/loader.js'></script></html>",
 "https://zapier.com":"<html><script src='//js.hs-scripts.com/123.js'></script></html>",
 "https://nimbusrealty.com":"""<html><title>Nimbus Realty - homes in Portland</title>
   <a href="/contact">Contact us</a></html>""",
 "https://nimbusrealty.com/contact":"""<html>Nimbus Realty - reach Sarah:
   <a href="mailto:sarah.lee@nimbusrealty.com">email</a> or info@nimbusrealty.com.
   Automated mail: noreply@nimbusrealty.com. Tracking pixel icon@2x.png</html>""",
}
CALLS=[]
def http_get(url, as_json=True, headers=None):
    CALLS.append(url)
    for k,v in R.items():
        if (k.startswith("https://") and url==k) or (not k.startswith("https://") and k in url):
            if isinstance(v,str):
                return None if as_json else v
            return json.loads(json.dumps(v)) if as_json else json.dumps(v)
    return None
