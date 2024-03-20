import asyncio
from pyppeteer import launch
from pyppeteer.errors import TimeoutError

async def connect(userAgent: str='', proxy: str=''):
    return await launch({
        'executablePath': 'D:/Program Files/Google/Chrome/Application/chrome.exe',
        'headless': True,
        'devtools': True,
        'autoClose': True,
        'userDataDir': '/dev/null',
        'args': [
            # '--lang=en',
            '--disable-infobars',
            # '--start-maximized',
            # '--no-sandbox',
            # f'--proxy-server="https={proxy}"',
            # f'--user-agent={userAgent}'
        ]
    })

async def getElement(page, xpath: str, property: str):
    try: await page.waitForXPath(xpath, timeout=3*1000)
    except TimeoutError: return ['']
    else: return [await (await _.getProperty(property)).jsonValue() for _ in (await page.xpath(xpath))]

async def main():
    browser = await connect()
    page = (await browser.pages())[0]
    
    await page.goto('https://funpay.com/')
    await page.waitFor(1000)
    print(await getElement(page, "//div[@id='MPH_SCROLL_TRIGGER']", 'href'))[0]

    await browser.close()

if __name__ == "__main__": 
    asyncio.run(main())