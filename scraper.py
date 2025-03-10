import requests
from bs4 import BeautifulSoup, Comment
import json 
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
    return None

def make_request_with_session(session, method, url, **kwargs):
    return session.request(method, url, **kwargs)

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
        response = backoff_request(make_request_with_session, session, "GET", url, timeout=5)
        if response is None:
            return 'Error'
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
        "Authorization": "Bearer RK8tJneU4qiuAN5FGuAeOgvsH-qKc_NaMM2niJWwkkZmCpU9odnsKuIWrWg-nPg-G8cp6Tu17dp1zruXQSMvD9hqeS3DLLwqQd1TZEIiNnKA920K1l89I-PLSnrPZ3Yx"
    }
    params = {
        "term": "business",
        "location": location,
        "radius": min(radius, 40000),
        "limit": 10 
    }
    
    response = backoff_request(make_request_with_session, session, "GET", url, headers=headers, params=params)
    
    if response and response.status_code == 200:
        print(f"Yelp API response status code: {response.status_code}")
        return response.json().get('businesses', [])
    print("Failed to retrieve businesses after retries.")
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
radius = 30000  # 25 miles in meters
businesses = get_businesses(location, radius)
print(f"Number of businesses found: {len(businesses)}")

# Initialize the Selenium WebDriver
driver = init_webdriver()

# Placeholders for business data to be saved in JSON format
business_data = []
unknown_business_data = []
not_founds_data = []



from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Assuming `extract_website` and `check_website` are defined elsewhere

for business in businesses:
    name = business.get('name', '')
    phone = business.get('phone', '')
    yelp_url = business.get('url', '')
    address = ", ".join(business.get('location', {}).get('display_address', []))

    business_info = {
        "Business Name": name,
        "Email": "",
        "Phone": phone,
        "Website": "",
        "Type": "Unknown",
        "Location": address
    }

    if yelp_url:
        print(f"Checking Yelp page: {yelp_url}")
        try:
            driver.get(yelp_url)
            
            # Wait until the element indicating page load is present (adjust selector as needed)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))  # Placeholder selector
            )

            # Extract website URL
            website_url = extract_website(driver)

            if website_url:
                site_type = check_website(website_url)
                email = ''

                try:
                    # Request website content with backoff
                    website_response = backoff_request(make_request_with_session, session, 'GET', website_url, headers=headers_with_agent, timeout=5, retries=3, base_delay=1, max_delay=8)
                    if website_response:
                        website_soup = BeautifulSoup(website_response.text, 'html.parser')
                        email = extract_email(website_soup) if website_soup else ''
                except requests.exceptions.RequestException as req_err:
                    print(f"Error accessing {website_url} for email extraction: {req_err}")

                # Update business info
                business_info.update({
                    "Email": email,
                    "Website": website_url,
                    "Type": site_type
                })

                # Append data based on site type
                if site_type == 'Unknown':
                    unknown_business_data.append(business_info)
                    print(f"Added {website_url} as 'Unknown' to unknowns.json.")
                else:
                    business_data.append(business_info)
                    print(f"Added {website_url} as '{site_type}' site to business data.")
            else:
                # No website found
                print(f"No website found for {name}. Adding to not-founds.json.")
                not_founds_data.append(business_info)
        except Exception as e:
            print(f"Failed to process {yelp_url}: {e}")

# Close the WebDriver
driver.quit()

# Write the collected data to JSON files
with open('businesses.json', 'w') as business_file:
    json.dump(business_data, business_file, indent=4)

with open('unknowns.json', 'w') as unknown_file:
    json.dump(unknown_business_data, unknown_file, indent=4)

with open('not-founds.json', 'w') as not_founds_file:
    json.dump(not_founds_data, not_founds_file, indent=4)

print("Data has been successfully saved to businesses.json, unknowns.json, and not-founds.json.")
