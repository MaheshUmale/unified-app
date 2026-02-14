import asyncio
import os
from tradingview import Client

import rookiepy
raw_cookies = rookiepy.brave(['.tradingview.com'])
if raw_cookies:
    session_token = next((c['value'] for c in raw_cookies if c['name'] == 'sessionid'), None)
    signature = next((c['value'] for c in raw_cookies if c['name'] == 'sessionid_sign'), None)

    print(session_token)
    print(signature)


    os.environ['TV_SESSION'] = session_token
    os.environ['TV_SIGNATURE'] = signature


    session = os.environ.get('TV_SESSION')
    signature = os.environ.get('TV_SIGNATURE')
else:
    os.environ['TV_SESSION'] = '04ldf2vb9uwfcayfs2mgtdwwli7jg82s'
    os.environ['TV_SIGNATURE'] = 'v3:SHw6hycY6WFsEgbr5vKI6ISfkr331Go/ovj3kaQyG1o='



    
async def main():
    client = Client(
        token=session_token,
        signature=signature
    )
    await client.connect()

    chart = client.Session.Chart()
    chart.set_market('BINANCE:BTCUSDT', {'timeframe': '1D'})

    def on_update():
        if chart.periods:
            print(f"Latest Price: {chart.periods[0].close}")

    chart.on_update(on_update)
    await asyncio.sleep(10)
    await client.end()

if __name__ == '__main__':
    asyncio.run(main())