# shellcheck disable=SC2009
ps -ef |grep -v grep|grep -v tail |grep crawl|awk '{print $2}'|xargs kill -9
# shellcheck disable=SC2009
ps -ef |grep -v grep|grep -v DingTalk|grep -v tail|grep Chrome|grep input|awk '{print $3}'|xargs kill -9

rm -rf ./build ./dist setup.py
py2applet --make-setup crawl.py  ./logo.png ./logo.ico

# shellcheck disable=SC2046
# shellcheck disable=SC2006
# shellcheck disable=SC2005
# shellcheck disable=SC2034
path=`pwd`
echo "${path}/setup.py"
sed -ie 12s/'OPTIONS = {}'/"OPTIONS = {'iconfile': '.\/logo.ico'}"/ setup.py
python3 setup.py py2app -A
rm -rf /Applications/Crawl.app
rm -rf /Applications/crawl.app
mv ./dist/Crawl.app /Applications/Crawl.app
