import json
import re
import statistics
import subprocess

from datetime import date, datetime, timedelta
from itertools import groupby
from logging import Logger
from operator import itemgetter
from random import randint
from requests.exceptions import ConnectionError
from time import sleep

from stl.endpoint.base_endpoint import BaseEndpoint
from stl.endpoint.pdp import Pdp
from stl.exception.api import ApiException

# ohwell. No time to debug why various request parameters and headers are
# needed or not needed to get a successful response.
# Much easier to just use the chrome devtools network tab to copy the XHR request
# data with right click, 'Copy / Copy as cURL' and paste it below.
#
# 1. Open up airbnb.com
# 2. Click on the very first listing
# 3. Let the page load, open up devtools
# 4. Go to the network tab
# 5. Clear all requests
# 6. Filter for XHR
# 7. Set some checkinDate and checkoutDate
# 8. Watch the network tab for the request
# 9. Right click on the request, 'Copy / Copy as cURL' and paste it below.
# optionally anonymize data
# Do a test run, watch for changed response data

class Curling:
    CURL = ""

    def subst(self, text, data):
        for key, repl in data.items():
            regex = f"{key}%22%3A%22(.*?)%22"
            tgt = f"{key}%22%3A%22{repl}%22"
            text = re.sub(regex, tgt, text)
        return text

    def exec(self, data, api_key):
        cmd = self.subst(self.CURL.strip(), data)

        regex = "'X-Airbnb-API-Key: (.*?)'"
        tgt = f"'X-Airbnb-API-Key: {api_key}'"
        cmd = re.sub(regex, tgt, cmd)

        regex = "-H 'Referer: .*?'"
        tgt = ""
        cmd = re.sub(regex, tgt, cmd)

        cmd = f"{cmd} --silent"

        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
        content = result.stdout
        return content


class PricingCurling(Curling):
    CURL = """
curl 'https://www.airbnb.com/api/v3/StayCheckoutSections?operationName=StayCheckoutSections&locale=en&currency=HUF&variables=%7B%22input%22%3A%7B%22businessTravel%22%3A%7B%22workTrip%22%3Afalse%7D%2C%22checkinDate%22%3A%222023-09-04%22%2C%22checkoutDate%22%3A%222023-09-06%22%2C%22guestCounts%22%3A%7B%22numberOfAdults%22%3A1%2C%22numberOfChildren%22%3A0%2C%22numberOfInfants%22%3A0%2C%22numberOfPets%22%3A0%7D%2C%22guestCurrencyOverride%22%3A%22HUF%22%2C%22listingDetail%22%3A%7B%7D%2C%22lux%22%3A%7B%7D%2C%22metadata%22%3A%7B%22internalFlags%22%3A%5B%22LAUNCH_LOGIN_PHONE_AUTH%22%5D%7D%2C%22org%22%3A%7B%7D%2C%22productId%22%3A%22U3RheUxpc3Rpbmc6NDUyNzE1NTg%3D%22%2C%22china%22%3A%7B%7D%2C%22addOn%22%3A%7B%22carbonOffsetParams%22%3A%7B%22isSelected%22%3Afalse%7D%7D%2C%22quickPayData%22%3Anull%7D%2C%22isLeanFragment%22%3Afalse%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22fe9b61222639b40eac7817d45f3a08a90fd25eac6bac9af3e3f7a6356bf2560a%22%7D%7D' \
  -H 'X-Airbnb-Prefetch: web' \
  -H 'sec-ch-ua: "Not)A;Brand";v="24", "Chromium";v="116"' \
  -H 'DNT: 1' \
  -H 'X-Airbnb-Supports-Airlock-V2: true' \
  -H 'X-CSRF-Token: null' \
  -H 'X-Airbnb-API-Key: d306zoyjsyarp7ifhu67rjxn52tv0t20' \
  -H 'sec-ch-ua-platform-version: "5.15.0"' \
  -H 'X-Niobe-Short-Circuited: true' \
  -H 'dpr: 1' \
  -H 'sec-ch-ua-platform: "Linux"' \
  -H 'device-memory: 8' \
  -H 'X-Airbnb-GraphQL-Platform-Client: minimalist-niobe' \
  -H 'X-Client-Version: d13783d41e93e8c4b262242093b2a932e82c26e8' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'X-CSRF-Without-Token: 1' \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36' \
  -H 'x-client-request-id: 0pn85jm0u5599n0vgfy690mbouxb' \
  -H 'viewport-width: 1264' \
  -H 'Content-Type: application/json' \
  -H 'Referer: https://www.airbnb.com/rooms/45271558?adults=1&category_tag=Tag%3A8536&enable_m3_private_room=true&photo_id=1171105929&search_mode=flex_destinations_search&check_in=2023-09-04&check_out=2023-09-06&source_impression_id=p3_1693044851_ltH8Hl7MuXL%2FL41u&previous_page_section_name=1000&federated_search_id=bb6c907c-8d72-468f-a871-8490ab026e18&guests=1' \
  -H 'ect: 4g' \
  -H 'X-Airbnb-GraphQL-Platform: web' \
  --compressed
"""


class Pricing(BaseEndpoint):
    API_PATH = '/api/v3/startStaysCheckout'

    def get_pricing(self, checkin: str, checkout: str, listing_id: str) -> dict:
        """Get pricing object for a listing for specific dates."""
        # Get raw price data
        product_id = Pdp.get_product_id(listing_id)
        rates = self.get_rates(product_id, checkin, checkout)
        sections = rates['data']['presentation']['stayCheckout']['sections']
        if not (sections['temporaryQuickPayData'] and sections['temporaryQuickPayData']['bootstrapPayments']):
            raise ValueError('Error retrieving pricing: {}'.format(sections['metadata']['errorData']['errorMessage']))

        quickpay_data = sections['temporaryQuickPayData']['bootstrapPayments']
        return self.__normalize_pricing(
            quickpay_data['productPriceBreakdown']['priceBreakdown'],
            (datetime.strptime(checkout, '%Y-%m-%d') - datetime.strptime(checkin, '%Y-%m-%d')).days
        )

    def _api_request(self, url: str, method: str = 'GET', data=None) -> dict:
        if data is None:
            data = {}

        attempts = 0
        headers = {'x-airbnb-api-key': self._api_key}
        max_attempts = 3
        while attempts < max_attempts:
            sleep(randint(0, 2))  # do a little throttling
            attempts += 1

            pc = PricingCurling()
            # response = requests.request(method, url, headers=headers, data=data)
            response = pc.exec(data, self._api_key)
            response_json = json.loads(response)

            errors = response_json.get('errors')
            if not errors:
                return response_json

            self.__handle_api_error(url, errors)

        raise ApiException(['Could not complete API {} request to "{}"'.format(method, url)])

    def get_rates(self, product_id: str, start_date: str, end_date: str):
        payload = {
            'locale':        self._locale,
            'currency':      self._currency,
            'checkinDate':           start_date,
            'checkoutDate':          end_date,
            'guestCurrencyOverride': self._currency,
            'productId':             product_id,
        }
        url = ''
        return self._api_request(url, payload)

        # return pc.exec(data, self._api_key)
        #
        # url = BaseEndpoint.build_airbnb_url(self.API_PATH, {
        #     'operationName': 'startStaysCheckout',
        #     'locale':        self._locale,
        #     'currency':      self._currency
        # })
        # payload = json.dumps({
        #     'operationName': 'startStaysCheckout',
        #     'variables':     {
        #         'input': {
        #             'businessTravel':        {
        #                 'workTrip': False
        #             },
        #             'checkinDate':           start_date,
        #             'checkoutDate':          end_date,
        #             'guestCounts':           {
        #                 'numberOfAdults':   1,
        #                 'numberOfChildren': 0,
        #                 'numberOfInfants':  0,
        #                 'numberOfPets':     0
        #             },
        #             'guestCurrencyOverride': self._currency,
        #             'lux':                   {},
        #             'metadata':              {
        #                 'internalFlags': [
        #                     'LAUNCH_LOGIN_PHONE_AUTH'
        #                 ]
        #             },
        #             'org':                   {},
        #             'productId':             product_id,
        #             'china':                 {},
        #             'quickPayData':          None
        #         }
        #     },
        #     'extensions':    {
        #         'persistedQuery': {
        #             'version':    1,
        #             'sha256Hash': '4a01261214aad9adf8c85202020722e6e05bfc7d5f3d0b865531f9a6987a3bd1'
        #         }
        #     }
        # })
        # return self._api_request(url, 'POST', payload)

    @staticmethod
    def __normalize_pricing(price_breakdown: dict, nights: int):
        """Normalize price line items. Throw ValueError if price data malformed."""
        price_items = price_breakdown['priceItems']
        if len(price_items) > 5:
            raise ValueError(
                'Unexpected extra section types:\n{}'.format(', '.join([pi['type'] for pi in price_items])))

        items = {}
        for type_name in ['ACCOMMODATION', 'AIRBNB_GUEST_FEE', 'CLEANING_FEE', 'DISCOUNT', 'TAXES']:
            type_items = [i for i in price_items if i['type'] == type_name]
            if not type_items:
                if type_name == 'ACCOMMODATION':
                    raise ValueError('No ACCOMMODATION pricing found: {}'.format(price_items))
                else:
                    continue  # Missing AIRBNB_GUEST_FEE, CLEANING_FEE, DISCOUNT or TAXES is ok

            if len(type_items) > 1:
                raise ValueError('Unexpected multiple section type: %s' % type_name)

            items[type_name] = type_items.pop()

        # Create normalized pricing object
        mega = 1_000_000  # one million
        price_accommodation = int(items['ACCOMMODATION']['total']['amountMicros']) / mega
        taxes = int(items['TAXES']['total']['amountMicros']) / mega if items.get('TAXES') else 0
        cleaning_fee = int(items['CLEANING_FEE']['total']['amountMicros']) / mega if items.get('CLEANING_FEE') else 0
        airbnb_fee = int(items['AIRBNB_GUEST_FEE']['total']['amountMicros']) / mega if items.get('AIRBNB_GUEST_FEE') else 0
        pricing = {
            'nights':              nights,
            'price_nightly':       price_accommodation / nights,
            'price_accommodation': price_accommodation,
            'price_cleaning':      cleaning_fee,
            'taxes':               taxes,
            'airbnb_fee':          airbnb_fee,
            'total':               int(price_breakdown['total']['total']['amountMicros']) / mega,
        }

        if items.get('DISCOUNT'):
            discount = -1 * (int(items['DISCOUNT']['total']['amountMicros']) / mega)
            pricing['discount'] = discount
            pricing['tax_rate'] = taxes / (price_accommodation + pricing['price_cleaning'] - discount)
            if items['DISCOUNT']['localizedTitle'] in ['Weekly discount', 'Weekly stay discount']:
                pricing['discount_monthly'] = None
                pricing['discount_weekly'] = discount / price_accommodation
            elif items['DISCOUNT']['localizedTitle'] in ['Monthly discount', 'Monthly stay discount']:
                pricing['discount_monthly'] = discount / price_accommodation
                pricing['discount_weekly'] = None
            else:
                raise ValueError('Unhandled discount type: %s' % items['DISCOUNT']['localizedTitle'])
        else:
            pricing['tax_rate'] = taxes / (price_accommodation + pricing['price_cleaning'])

        return pricing


class Calendar(BaseEndpoint):
    API_PATH = '/api/v3/PdpAvailabilityCalendar'
    N_MONTHS = 12  # number of months of data to return; 12 months == 1 year

    def __init__(self, api_key: str, currency: str, logger: Logger, pricing: Pricing):
        super().__init__(api_key, currency, logger)
        self.__pricing = pricing
        self.__today = datetime.today()

    @staticmethod
    def get_date_ranges(status: str, booking_calendar: dict) -> list:
        """Given a booking calendar and a status of "available" or "booked", return a list of date range objects for
        either available or booked dates.
        """
        allowed_status = ['available', 'booked']
        if status not in allowed_status:
            raise ValueError('status must be one of "available" or "booked"')
        dates = [
            datetime.strptime(dt, '%Y-%m-%d').toordinal() for dt, is_booked in booking_calendar.items() if is_booked
        ] if status == 'booked' else [
            datetime.strptime(dt, '%Y-%m-%d').toordinal() for dt, is_booked in booking_calendar.items() if not is_booked
        ]
        ranges = []
        for k, g in groupby(enumerate(dates), lambda i: i[0] - i[1]):
            group = list(map(itemgetter(1), g))
            start_date = date.fromordinal(group[0])
            end_date = date.fromordinal(group[-1]) + timedelta(days=1)
            ranges.append({
                'start':  start_date,
                'end':    end_date,
                'length': (end_date - start_date).days
            })

        return ranges

    def get_calendar(self, listing_id: str) -> tuple:
        url = self.get_url(listing_id)
        response_data = self._api_request(url)
        return self.__get_booking_calendar(response_data)

    def get_rate_data(
            self,
            listing_id: str,
            ranges: list,
            min_nights: int = None,
            max_nights: int = None,
            full_data: bool = False
    ) -> dict:
        test_lengths = self.__get_test_lengths(max_nights, min_nights)
        pricing_data = {}
        for test_length in test_lengths:
            if test_length > max_nights:
                continue
            if test_length < min_nights:
                continue

            possible_ranges = [r for r in ranges if r.get('length') >= test_length]
            pd = None
            while possible_ranges and not pd:
                test_range = possible_ranges.pop()
                start_time = test_range['start'].strftime('%Y-%m-%d')
                end_time = (test_range['start'] + timedelta(days=test_length)).strftime('%Y-%m-%d')
                try:
                    pd = self.__pricing.get_pricing(start_time, end_time, listing_id)
                except (ValueError, RuntimeError) as e:
                    # ValueError or Response error
                    self._logger.error('{}: Could not get pricing data: {}'.format(listing_id, str(e)))
                    continue
                except ConnectionError as e:
                    self._logger.error('{}: Could not get pricing data: {}'.format(listing_id, str(e)))
                    # connection error due to network issues. wait for one minute for network connection to be
                    # re-established.
                    sleep(60)
                    continue

            if not pd:
                self._logger.warning('{}: Unable to find available {} day range'.format(listing_id, test_length))
                continue

            pricing_data[test_length] = pd

        if full_data or not pricing_data:
            return pricing_data

        # normalize data
        test_pricing = list(pricing_data.values()).pop()
        pricing_doc = {
            'price_nightly':  test_pricing['price_nightly'],
            'price_cleaning': test_pricing['price_cleaning'],
        }

        if pricing_data.get(7) and pricing_data[7].get('discount_weekly'):
            pricing_doc['discount_weekly'] = pricing_data[7]['discount_weekly']

        monthly_length = min_nights if min_nights > 28 else 28
        if pricing_data.get(monthly_length) and pricing_data[monthly_length].get('discount_monthly'):
            pricing_doc['discount_monthly'] = pricing_data[monthly_length]['discount_monthly']

        return pricing_doc

    def get_url(self, listing_id: str) -> str:
        """Get PdpAvailabilityCalendar URL."""
        query = {
            'operationName': 'PdpAvailabilityCalendar',
            'locale':        self._locale,
            'currency':      self._currency,
            'variables':     {
                "request": {
                    'count':     self.N_MONTHS,
                    'listingId': listing_id,
                    'month':     self.__today.month,
                    'year':      self.__today.year
                }
            },
            'extensions':    {
                'persistedQuery': {
                    'version':    1,
                    'sha256Hash': '8f08e03c7bd16fcad3c92a3592c19a8b559a0d0855a84028d1163d4733ed9ade'
                }
            }
        }
        self._put_json_param_strings(query)

        return BaseEndpoint.build_airbnb_url(self.API_PATH, query)

    @staticmethod
    def __get_test_lengths(max_nights: int, min_nights: int) -> list:
        """Generate a list of lengths of stays to be used to determine pricing, based upon listing requirements of
        max_nights and min_nights."""
        if min_nights > 28:  # monthly only
            return [min_nights]
        elif min_nights >= 7:
            if max_nights >= 28:  # weekly and monthly
                return [min_nights, 28]
            else:  # weekly only
                return [min_nights]
        else:  # min nights < 7
            if max_nights >= 28:  # daily, weekly, and monthly
                return [min_nights, 7, 28]
            elif max_nights >= 7:  # daily and weekly
                return [min_nights, 7]
            else:  # daily only
                return [min_nights]

    def __get_booking_calendar(self, data: dict) -> tuple:
        calendar_months = data['data']['merlin']['pdpAvailabilityCalendar']['calendarMonths']
        first_available_date = None
        booking_calendar = {}
        for month in calendar_months:
            booked_days = total_days = 0
            for day in month['days']:
                total_days += 1
                calendar_date = datetime.strptime(day['calendarDate'], '%Y-%m-%d')
                if calendar_date < self.__today:
                    continue  # skip dates in the past

                # is either today or in the future
                if day['available']:
                    if first_available_date is None:
                        first_available_date = day['calendarDate']
                    booking_calendar[day['calendarDate']] = False
                else:
                    booking_calendar[day['calendarDate']] = True
                    booked_days += 1

        min_nights = statistics.mode([day['minNights'] for month in calendar_months for day in month['days']])
        max_nights = statistics.mode([day['maxNights'] for month in calendar_months for day in month['days']])

        return booking_calendar, min_nights, max_nights
