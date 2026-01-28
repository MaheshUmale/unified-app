import rookiepy
from tvDatafeed import TvDatafeed, Interval

# 1. Get cookies from your browser
cookies = rookiepy.to_cookiejar(rookiepy.brave(['.tradingview.com']))

# 2. Initialize TvDatafeed with cookies
tv = TvDatafeed(cookies=cookies)

# 3. Get data
df = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_daily, n_bars=10)
print(df)
