from bs4 import BeautifulSoup
import requests
from parsel import Selector 
import sys
import logging 
from tenacity import retry, wait_random, stop_after_attempt
