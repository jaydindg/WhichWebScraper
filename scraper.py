import requests
from bs4 import BeautifulSoup, Comment
import csv
import re
from urllib.parse import urlparse, parse_qs, unquote
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import random

# Define a user-agent to simulate browser requests
headers_with_agent = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"
}

# Initialize a session for cookie management
session = requests.Session()
session.headers.update(headers_with_agent)

# Initialize Selenium WebDriver
def init_webdriver():
    options = Options()
    options.add_argument('--headless')  # Optional: run in headless mode if desired
    options.add_argument('--no-sandbox')  # Optional: disable sandboxing for better compatibility
    options.add_argument('--disable-dev-shm-usage')  # Optional: overcome limited resource problems

    # Use the ChromeDriverManager to get the executable path for ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def random_delay(min_delay=1, max_delay=3):
    time.sleep(random.uniform(min_delay, max_delay))

# Implement backoff strategy for retries
def backoff_request(func, *args, retries=3, base_delay=1, max_delay=16, **kwargs):
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1}/{retries} failed: {e}")
            random_delay(base_delay, min(base_delay * 2 ** attempt, max_delay))
    return None  # Return None if all attempts fail

# (Existing website checks unchanged...)

def check_website(url):
    if not url:
        return 'Error'
    try:
        response = backoff_request(session.get, url, timeout=5)
        if response is None:
            return 'Error'
        soup = BeautifulSoup(response.text, 'html.parser')
        headers = response.headers

        # (Existing checks unchanged...)

        return 'Unknown'
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {url}: {e}")
        return 'Error'

def is_squarespace(soup):
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    return any("This is Squarespace." in comment for comment in comments)

def is_wix(soup, headers):
    if 'X-Wix-Meta-Site-Id' in headers:
        return True
    wix_comments = [
        "wix",
        "wix-first-pain",
        "<!--pageHtmlEmbeds.bodyStartstart-->",
    ]
    return any(comment in str(soup) for comment in wix_comments)

def is_webflow(soup):
    webflow_comments = [
        "<!-- Injecting site-wide to the head -->",
        "<!-- End Injecting site-wide to the head -->",
        "<!-- Inject secured cdn script -->",
        "<!-- PWA settings -->",
        "<!-- ========= Site Content ========= -->"
    ]
    return any(comment in str(soup) for comment in webflow_comments)

def is_nextjs(soup):
    return '/_next/static' in str(soup)

def is_shopify(soup):
    shopify_comments = [
        "myshopify.com",
        "/shopifycloud"
    ]
    return any(comment in str(soup) for comment in shopify_comments)

def is_leadpages(soup):
    leadpages_comments = [
        "<!-- BUILT WITH LEADPAGES https://www.leadpages.com -->",
    ]
    return any(comment in str(soup) for comment in leadpages_comments)

def is_wordpress(soup, url):
    if (soup.find('meta', {'name': 'generator', 'content': 'WordPress'}) or
            soup.find('link', {'rel': 'https://api.w.org/'})):
        return True
    if '/wp-content' in soup.prettify():
        return True
    wp_admin_url = f"{url.rstrip('/')}/wp-admin/"
    try:
        response = requests.get(wp_admin_url, headers=headers_with_agent, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def check_website(url):
    if not url:
        return 'Error'
    try:
        response = requests.get(url, headers=headers_with_agent, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        headers = response.headers

        if is_squarespace(soup):
            return 'Squarespace'
        if is_wix(soup, headers):
            return 'Wix'
        if is_webflow(soup):
            return 'Webflow'
        if is_wordpress(soup, url):
            return 'WordPress'
        if is_nextjs(soup):
            return 'Next.js'
        if is_shopify(soup):
            return 'Shopify'
        if is_leadpages(soup):
            return 'Leadpages'

        return 'Unknown'
    except requests.exceptions.HTTPError as e:
        print(f"Error accessing {url}: {e}")
        return 'Error'
    except requests.exceptions.RequestException as e:
        print(f"General request error for {url}: {e}")
        return 'Error'

def get_businesses(location, radius):
    print(f"Fetching businesses for location: {location}")
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {
        "Authorization": "Bearer WfINueq9VYVrwz0hmtuoRY6L-EMRxCjVh9jFy31adPovm6Sg8_uRwwA6JncBB2dpziY7_ESMnc6_IyyRdgvrY1gNtRIfSzXScNev8pRW0cUobycQxZgNE9c2uEInZ3Yx"
    }
    params = {
        "term": "business",
        "location": location,
        "radius": min(radius, 40000),
        "limit": 50
    }
    response = requests.get(url, headers=headers, params=params)
    print(f"Yelp API response status code: {response.status_code}")
    if response.status_code == 200:
        return response.json().get('businesses', [])
    return []

def extract_yelp_url(yelp_url):
    parsed_url = urlparse(yelp_url)
    query_params = parse_qs(parsed_url.query)
    encoded_url = query_params.get('url', [None])[0]
    return unquote(encoded_url) if encoded_url else ''

def extract_email(soup):
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', str(soup))
    return emails[0] if emails else ''


def extract_website(driver):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Wait for the page to fully load and the website link to be present
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'y-css-8hdzny')))
            random_delay()  # Random delay before fetching links
            
            links = driver.find_elements(By.CLASS_NAME, 'y-css-8hdzny')
            print(f"Attempt {attempt + 1}: Found {len(links)} links with class 'y-css-8hdzny'.")

            for link in links:
                href = link.get_attribute('href')
                print(f"Href: '{href}'")

                if 'biz_redir' in href:
                    match = re.search(r'url=(http[^&]+)', href)
                    if match:
                        encoded_url = match.group(1)
                        website_link = unquote(encoded_url)
                        print(f"Extracted website link: '{website_link}'")
                        return website_link
            
            print("No valid website link found.")
            break
        except Exception as e:
            print(f"Error finding website link: {e}")
            random_delay(2, 4)  # Random delay before retrying
            if attempt == max_retries - 1:
                print("Max retries reached. Could not find the website link.")
                return ''

    return ''


# Main program
location = 'St. Louis, MO'
radius = 40000  # 25 miles in meters
businesses = get_businesses(location, radius)
print(f"Number of businesses found: {len(businesses)}")

# Open files for writing
with open('businesses.csv', mode='w', newline='') as file, \
     open('unknowns.csv', mode='w', newline='') as unknown_file:
    
    writer = csv.writer(file)
    writer.writerow(['Business Name', 'Email', 'Phone', 'Website', 'Type', 'Location'])

    unknown_writer = csv.writer(unknown_file)
    unknown_writer.writerow(['Business Name', 'Email', 'Phone', 'Website', 'Location'])

    # Initialize the Selenium WebDriver
    driver = init_webdriver()

    for business in businesses:
        name = business.get('name', '')
        phone = business.get('phone', '')
        yelp_url = business.get('url', '')
        address = ", ".join(business.get('location', {}).get('display_address', []))

        if yelp_url:
            print(f"Checking Yelp page: {yelp_url}")
            try:
                driver.get(yelp_url)
                time.sleep(2)  # Optional: wait for additional content to load
                
                # Use the new website extraction logic
                website_url = extract_website(driver)

                if website_url:
                    site_type = check_website(website_url)
                    email = ''
                    try:
                        website_response = requests.get(website_url, headers=headers_with_agent, timeout=5)
                        website_soup = BeautifulSoup(website_response.text, 'html.parser')
                        email = extract_email(website_soup)
                    except requests.exceptions.RequestException:
                        print(f"Error accessing {website_url} for email extraction.")

                    if site_type == 'Unknown':
                        unknown_writer.writerow([name, email, phone, website_url, address])
                        print(f"{website_url} is an Unknown site. Writing to unknowns.csv.")
                    else:
                        writer.writerow([name, email, phone, website_url, site_type, address])
                        print(f"{website_url} is a {site_type} site.")
                else:
                    print(f"No website found for {name}. Writing partial info to CSV.")
                    writer.writerow([name, '', phone, '', 'Unknown', address])
            except Exception as e:
                print(f"Failed to process {yelp_url}: {e}")
    
    # Close the WebDriver
    driver.quit()
