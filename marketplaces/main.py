import asyncio
import aioschedule as schedule
from pyppeteer import launch
from pyppeteer_stealth import stealth
from pyppeteer.errors import TimeoutError
import gspread
from gspread.utils import rowcol_to_a1
from urllib.parse import urlparse
import yaml
import re
from datetime import datetime
from time import sleep
import random

async def connect(userAgent: str='', proxy: str=''):
    # return await launch({'headless': False, 'autoClose': True, 'slowMo': 10, })#'args': ['--disable-infobars', '--no-sandbox', f'--user-agent={userAgent}']})
    return await launch({
        # 'executablePath': 'D:/Program Files/Google/Chrome/Application/chrome.exe',
        'headless': False,
        'devtools': False,
        'autoClose': False,
        'args': [
            # '--lang=en',
            '--disable-infobars',
            # '--incognito',
            # '--start-maximized',
            # '--no-sandbox',
            # f'--proxy-server="https={proxy}"',
            f'--user-agent={userAgent}'
        ]
    })

async def getElement(page, xpath: str, properties):
    try: await page.waitForXPath(xpath, timeout=10*1000)
    except TimeoutError: 
        # print('timeout xpath')
        return ['']
    else: 
        data = []
        for _ in await page.xpath(xpath):
            data.append([await (await _.getProperty(property)).jsonValue() for property in properties] if isinstance(properties, list) else await (await _.getProperty(properties)).jsonValue())
        return data

async def slicer(list_, chunk, browser, act): return sum([await asyncio.gather(*[act(browser, *_) for _ in list_[i:i + chunk]]) for i in range(0, len(list_), chunk)], [])

async def getPrice(browser, url):
    try:
        # sleep(round(random.uniform(1.0, 10.0), 2))
        page = await browser.newPage()
        await stealth(page)
        
        response = await page.goto(url, timeout=0)
        await page.waitFor(1000)
        
        await page.reload()
        await page.waitFor(1000)
        
        # print(response.request.headers)
        
        domain = urlparse(url).netloc
        # print(domain)
        with open('config.yaml') as f: config = yaml.load(f, Loader=yaml.FullLoader)
        xpath_dict = {
            'www.ozon.ru': config['ozon-xpath'],
            'www.wildberries.ru': config['wb-xpath'],
            'market.yandex.ru': config['ym-xpath'],
            'megamarket.ru': config['mg-xpath']
        }
        price = (await getElement(page, xpath_dict[domain], 'textContent'))[0].strip()
        await page.close()
        return price
    except Exception as e:
        print('getPrice', e)
        await page.reload()
        await getPrice(browser, url)
    
async def getUrls(sht):
    urls = {}
    try:
        for w in sht.worksheets():
            place = w.find('Ссылка')
            if place: urls.update({w: [{'index': i, 'url': _} for i, _ in enumerate(w.col_values(place.col)[place.row + 1:], place.row + 2) if _ not in ['', 'None']]})
            else: urls.update({w: None})
    except Exception as e: 
        # print('getUrls', e)
        await getUrls(sht)
    else: return urls

async def getPrices(w): 
    try: 
        place = w.find(re.compile(r'Цена.*'))
        if place.value == f"Цена {datetime.now().strftime('%d.%m')}": return False, place
        else: return True, place
    except Exception as e: 
        # print('getPrices', e)
        await getPrices(w)

getInt = lambda _: int(re.search(r'\d+', ('').join(re.compile(r'[\d₽]', re.UNICODE).findall(_)))[0])

async def updateCell(w, cell, price):
    try:
        old_price = w.cell(cell[0], cell[1] + 1).value
        old_price_num = getInt(old_price) if old_price and old_price != 'None' else 0
        new_price = price
        new_price_num = getInt(new_price) if new_price and new_price != '' else 0
        # print(old_price_num, new_price_num)
        if old_price_num > new_price_num: r, g, b = (1.0, 0.0, 0.0)
        elif old_price_num < new_price_num: r, g, b = (0.0, 1.0, 0.0)
        else: r, g, b = (1.0, 1.0, 0.0)
        if new_price == '': r, g, b = (1.0, 0.0, 0.0)
        w.update_cell(*cell, f'{new_price_num} ₽')
        w.format(
            rowcol_to_a1(*cell), 
            {'backgroundColor': {
                'red': r,
                'green': g,
                'blue': b
            }}
        )
    except Exception as e: 
        # print('updateCell', e)
        await updateCell(w, cell, price)

async def main(day, time_):
    with open('config.yaml') as f: config = yaml.load(f, Loader=yaml.FullLoader)
    
    browser = await connect(userAgent=config['user-agent'])
    
    gc = gspread.service_account(filename='auth.json')
    
    print(f'\n{day.title()} {time_} starting...')
    for place, body in zip(config['places'], await asyncio.gather(*[getUrls(sht) for sht in [gc.open_by_url(config[sht_url]) for sht_url in config['places']]])): # ['ozon-url', 'wb-url', 'ym-url', 'mg-url']
        print(f"\t{place.replace('-url', '')}: ")
        if body:
            for w, cells in body.items():
                print(f'\t\t{w.title}')
                if cells:
                    for cell, price in zip(cells, await slicer([[cell['url']] for cell in cells], config['pages-chunk'], browser, getPrice)):
                        price_column = await getPrices(w)
                        update_, price_column = price_column if price_column else (None, None)
                        # print(cell, repr(price))
                        # print(update_, price_column)
                        
                        if price_column: 
                            if update_:
                                while True:
                                    try:
                                        w.insert_cols(values=[[]], col=price_column.col, inherit_from_before=False)
                                        w.update_cell(price_column.row, price_column.col, f"Цена {datetime.now().strftime('%d.%m')}")
                                    except: pass
                                    else: break
                            await updateCell(w, (cell['index'], price_column.col), price)
                    
    await browser.close()

if __name__ == '__main__': 
    while True:
        try:
            with open('config.yaml') as f: config = yaml.load(f, Loader=yaml.FullLoader)
            for day, time_ in zip(config['days'], config['times']):
                getattr(schedule.every(), day).at(time_).do(main, day, time_)
            print('Schedule: ')
            print(*[f'\t{_.start_day.title()} - {_.at_time}' for _ in schedule.jobs], sep='\n')
            loop = asyncio.new_event_loop()
        except Exception as e: 
            print(e)
            sleep(5)
        while True:
            with open('config.yaml') as f: check = yaml.load(f, Loader=yaml.FullLoader)
            if config != check:
                schedule.clear()
                print('\nreboot...\n')
                break
            else: loop.run_until_complete(schedule.run_pending())
            sleep(0.1)