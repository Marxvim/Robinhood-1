from .order import Order, CryptoOrder
from .quote import Quote, CryptoQuote

from six.moves.urllib.request import getproxies
from six.moves import input

import getpass
import requests
import uuid
import pickle

from . import endpoints
from . import crypto_endpoints
from .crypto_endpoints import crypto_pairs as _crypto_pairs
from six.moves.urllib.parse import unquote
from json import dumps


class Trader:

    client_id = "c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS"

    ###########################################################################
    #                       Logging in and initializing
    ###########################################################################

    def __init__(self, username=None, password=None):
        self.auth_token = None
        self.session = requests.session()
        self.session.proxies = getproxies()
        self.refresh_token = None
        self.session.headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en;q=1, fr;q=0.9, de;q=0.8, ja;q=0.7, nl;q=0.6, it;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-robinhood-API-Version": "1.265.0",
            "Connection": "keep-alive",
            "User-Agent": "robinhood/823 (iPhone; iOS 7.1.2; Scale/2.00)"
        }

        if password:
            assert username
        if username:
            self.login(username, password)

    def login(self, username=None, password=None, mfa_code=None, device_token=None):
        """Login to Robinhood
        Args:
            username (str): username
            password (str): password

        Returns:
            (bool): received valid auth token

        """
        if not username:
            username = input("username: ")
        if not password:
            print('password:', end='')
            password = getpass.getpass()
        if not device_token:
            device_token = uuid.uuid1()

        payload = {
            'username': username,
            'password': password,
            'grant_type': 'password',
            'device_token': device_token.hex,
            "token_type": "Bearer",
            'expires_in': 603995,
            "scope": "internal",
            'client_id': self.client_id,
        }

        if mfa_code:
            payload['access_token'] = self.auth_token
            payload['mfa_code'] = mfa_code
        else:
            payload['challenge_type'] = 'sms'

        res = self.session.post(endpoints.login(), data=payload, timeout=15, verify=True)
        res.raise_for_status()
        data = res.json()

        if 'mfa_required' in data.keys():
            mfa_code = input("MFA: ")
            return self.login(username, password, mfa_code, device_token)

        if 'access_token' in data.keys() and 'refresh_token' in data.keys():
            self.auth_token = data['access_token']
            self.refresh_token = data['refresh_token']
            self.session.headers['Authorization'] = 'Bearer ' + self.auth_token
            return res

        return False

    def logout(self):
        """Logout from robinhood

        Returns:
            (:obj:`requests.request`) result from logout endpoint

        """
        payload = {
            'client_id': self.client_id,
            'token': self.refresh_token
        }
        res = self.session.post(endpoints.logout(), data=payload, timeout=15)
        self.session.headers['Authorization'] = None
        self.auth_token = None
        res.raise_for_status()
        return res

    def _req_get(self, *args, timeout=15, asjson=True, **kwargs):
        res = self.session.get(*args, timeout=timeout, **kwargs)
        res.raise_for_status()
        return res.json() if asjson else res

    def _req_post(self, *args, timeout=15, asjson=True, **kwargs):
        """Should be used for api calls only (not login)"""
        self.session.headers['Content-Type'] = 'application/json'
        self.session.headers['Accept'] = '*/*'
        self.session.headers['Sec-Fetch-Site'] = 'same-site'
        self.session.headers['Sec-Fetch-Mode'] = 'cors'
        self.session.headers['Accept-Encoding'] = 'gzip, deflate, br'
        self.session.headers['Accept-Language'] = 'en-US,en;q=0.9'
        res = self.session.post(*args, timeout=timeout, **kwargs)
        res.raise_for_status()
        return res.json() if asjson else res

    ###########################################################################
    #                        SAVING AND LOADING SESSIONS
    ###########################################################################

    def save_session(self, session_name):
        """Save your python session to avoid logging in again,
            reload with `Trader.load_session(session_name)`"""
        with open(session_name, 'wb') as file:
            pickle.dump(self, file)

    @staticmethod
    def load_session(session_name):
        """load a pickled Trader object created from `save_session`"""
        with open(session_name, 'rb') as file:
            return pickle.load(file)

    ###########################################################################
    #                               GET DATA
    ###########################################################################

    def fundamentals(self, symbol):
        """Fetch fundamentals info"""
        return self._req_get(endpoints.fundamentals(symbol.upper()))

    def instrument(self, symbol):
        """Fetch instrument info"""
        url = str(endpoints.instruments()) + "?symbol=" + str(symbol)
        results = self._req_get(url)['results'][0]
        return results if results else Exception(f"Invalid symbol: {symbol}")

    def quote(self, symbol):
        """Fetch stock quote"""
        symbol = symbol.upper()
        crypto_symbol = symbol + 'USD'
        if crypto_symbol in _crypto_pairs:
            url = str(crypto_endpoints.quotes(_crypto_pairs[crypto_symbol]))
            return CryptoQuote(self._req_get(url))

        url = str(endpoints.quotes()) + f"?symbols={symbol}"
        return Quote(self._req_get(url)['results'][0])

    def historical_quotes(self, symbol, interval, span, bounds='regular'):
        """Fetch historical data for stock

            Note: valid interval/span configs
                interval = 5minute | 10minute + span = day, week
                interval = day + span = year
                interval = week

            Args:
                symbol (str): stock ticker
                interval (str): resolution of data
                span (str): length of data
                bounds (:enum:`Bounds`, optional): 'extended' or 'regular' trading hours

            Returns:
                (:obj:`dict`) values returned from `historicals` endpoint
        """
        crypto_symbol = symbol.upper() + 'USD'
        if crypto_symbol in _crypto_pairs:
            raise NotImplemented("historical quotes is not supported for crypto-currencies")

        symbol = symbol if isinstance(symbol, list) else [symbol]
        assert(bounds in ['immediate', 'regular'])

        url = endpoints.historicals()
        params = {
            'symbols': ','.join(symbol).upper(),
            'interval': interval,
            'span': span,
            'bounds': bounds
        }
        url += '?' + '&'.join([f'{k}={v}' for k,v in params.items() if v])
        return self._req_get(url)['results'][0]

    ###########################################################################
    #                               Account Data
    ###########################################################################

    def account(self):
        res = self._req_get(endpoints.accounts())
        return res['results'][0]

    def crypto_account(self):
        res = self._req_get(crypto_endpoints.accounts())
        return res['results'][0]

    def portfolio(self):
        """Returns the first portfolio result, current rb only supports 1 portfolio"""
        return self._req_get(endpoints.portfolios())['results'][0]

    def orders(self):
        orders = self._req_get(endpoints.orders())['results']
        return [Order(self, order, False) for order in orders]

    def order(self, order:[dict, str]):
        order_id = order['id'] if isinstance(order, dict) else order
        json = self._req_get(endpoints.orders() + order_id)
        return Order(self, json, False)

    def crypto_orders(self):
        orders = self._req_get(crypto_endpoints.orders())['results']
        return [CryptoOrder(self, order, False) for order in orders]

    def crypto_order(self, order):
        order_id = order['id'] if isinstance(order, dict) else order
        json = self._req_get(crypto_endpoints.orders() + order_id)
        return CryptoOrder(self, json, False)

    def dividends(self):
        return self._req_get(endpoints.orders())

    def positions(self):
        return self._req_get(endpoints.positions())

    ###########################################################################
    #                               PLACE ORDER
    ###########################################################################
    def buy(self,
            symbol,
            quantity,
            price=None,
            stop_price=None,
            trailing_stop_percent=None,
            trailing_stop_amount=None,
            time_in_force=None,
            extended_hours=False):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns: Order object
        """
        return self.place_order(symbol=symbol,
                                quantity=quantity,
                                price=price,
                                side='buy',
                                stop_price=stop_price,
                                trailing_stop_percent=trailing_stop_percent,
                                trailing_stop_amount=trailing_stop_amount,
                                time_in_force=time_in_force,
                                extended_hours=extended_hours)

    def sell(self,
             symbol,
             quantity,
             price=None,
             stop_price=None,
             trailing_stop_percent=None,
             trailing_stop_amount=None,
             time_in_force=None,
             extended_hours=False):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns: (Order Object) (non-mutable dict)
        {
           "account_id":"<account_id>>",
           "average_price":"None",
           "cancel_url":"<cancel_url>>",
           "created_at":"2020-03-31T16:27:40.737772-04:00",
           "cumulative_quantity":"0.000000000000000000",
           "currency_pair_id":"3d961844-d360-45fc-989b-f6fca761d511",
           "executions":[],
           "id":"<guid>",
           "last_transaction_at":"None",
           "price":"6504.900000000000000000",
           "quantity":"0.000082200000000000",
           "ref_id":"<guid>>",
           "rounded_executed_notional":"0.00",
           "side": "sell"
           "state": ??
           "time_in_force":"gtc" or "gfd"
           "type":"market",
           "updated_at":"2020-03-31T16:27:40.866278-04:00"
        }
        """
        return self.place_order(symbol=symbol,
                                quantity=quantity,
                                price=price,
                                side='sell',
                                stop_price=stop_price,
                                trailing_stop_percent=trailing_stop_percent,
                                trailing_stop_amount=trailing_stop_amount,
                                time_in_force=time_in_force,
                                extended_hours=extended_hours)

    def _fprice(self, value):
        if not value:
            return value
        else:
            return "{0:.2f}".format(round(float(value), 2))

    def place_order(self,
                    symbol,
                    quantity,
                    side,
                    price=None,
                    trailing_stop_percent=None,
                    trailing_stop_amount=None,
                    stop_price=None,
                    time_in_force=None,
                    extended_hours=None):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns:
            (Order Object) (non-mutable dict)

            Example:
            {
               "account_id":"<account_id>>",
               "average_price":"None",
               "cancel_url":"<cancel_url>>",
               "created_at":"2020-03-31T16:27:40.737772-04:00",
               "cumulative_quantity":"0.000000000000000000",
               "currency_pair_id":"3d961844-d360-45fc-989b-f6fca761d511",
               "executions":[],
               "id":"<guid>",
               "last_transaction_at":"None",
               "price":"6504.900000000000000000",
               "quantity":"0.000082200000000000",
               "ref_id":"<guid>>",
               "rounded_executed_notional":"0.00",
               "side": "buy"
               "state" or "status": 'filled' or 'canceled' or 'pending'
               "time_in_force":"gtc" or "gfd"
               "type":"market",
               "updated_at":"2020-03-31T16:27:40.866278-04:00"
            }
        """
        symbol = symbol.upper()

        if symbol + 'USD' in _crypto_pairs:
            func = self._place_crypto_order_detail
            instrument = symbol + 'USD'
            if not time_in_force: time_in_force = 'gtc'
            assert(time_in_force == 'gtc')
            order_type = CryptoOrder
        else:
            func = self._place_order_detail
            instrument = self.instrument(symbol)
            if not time_in_force: time_in_force = 'gfd'
            order_type = Order

        assert(side in ['buy', 'sell'])
        assert(time_in_force in ['gfd', 'gtc'])

        json_result = func(
            instrument,
            quantity,
            price,
            stop_price,
            trailing_stop_percent,
            trailing_stop_amount,
            side,
            time_in_force,
            extended_hours)

        return order_type(self, json_result)

    def _place_order_detail(self,
                            instrument,
                            quantity,
                            price,
                            stop_price,
                            trailing_stop_percent,
                            trailing_stop_amount,
                            side,
                            time_in_force,
                            extended_hours):

        stop_args = [trailing_stop_amount, trailing_stop_percent, stop_price]
        if sum([bool(sa) for sa in stop_args]) > 1:
            raise Exception("stops arguments are mutually exclusive "
                            "(stop_price, trailing_stop_price, trailing_stop_percent)")

        is_trailing_stop = any([trailing_stop_percent, trailing_stop_amount])
        is_stop = stop_price or is_trailing_stop
        trigger = 'stop' if is_stop else 'immediate'
        order = 'limit' if price else 'market'

        if not (is_trailing_stop and side == 'sell') and not price:
            price = self._fprice(self.quote(instrument['symbol']).ask)

        payload = {
            "account": self.account()["url"],
            "instrument": unquote(instrument["url"]),
            "symbol": instrument["symbol"],
            "quantity": quantity,
            "side": side,
            "type": order.lower(),
            "trigger": trigger,
            "time_in_force": time_in_force,
            'price': price,
            'stop_price': stop_price,
            'extended_hours': 'true' if extended_hours else 'false'
        }

        if trailing_stop_amount or trailing_stop_percent:
            quote = self.quote(instrument['symbol']).ask

            if trailing_stop_amount:
                trailing_peg = {
                    'type': 'price',
                    'price': {
                        'amount': trailing_stop_amount,
                        'currency_code': 'USD'
                    }
                }

                modifier = -1 if side == 'sell' else 1
                stop_price = quote + trailing_stop_amount * modifier
                print(quote, trailing_stop_amount, modifier)
                payload['stop_price'] = self._fprice(stop_price)
            else:
                if not isinstance(trailing_stop_percent, int):
                    raise Exception("trailing stop percent must be int")

                trailing_peg = {
                    'type': 'percentage',
                    'percentage': trailing_stop_percent
                }

                trailing_stop_ratio = trailing_stop_percent/100
                if side == 'buy': trailing_stop_ratio += 1
                payload['stop_price'] = self._fprice(quote * trailing_stop_ratio)

            payload['trailing_peg'] = trailing_peg

        payload = {k:v for k,v in payload.items() if v}
        payload = dumps(payload)
        return self._req_post(endpoints.orders(), data=payload)

    def _place_crypto_order_detail(self,
                                   symbol,
                                   quantity,
                                   price,
                                   stop_price,
                                   trailing_stop_percent,
                                   trailing_stop_amount,
                                   side,
                                   time_in_force,
                                   extended_hours):

        if extended_hours is not None:
            raise Exception("extended hours is not a valid argument for crypto")

        if trailing_stop_amount or trailing_stop_percent or stop_price:
            raise Exception(
                "trailing_stop_amount, trailing_stop_percent, and stop_price, "
                "are not supported arguments for crypto-currencies")

        trigger = 'stop' if stop_price else 'immediate'
        order = 'limit' if price else 'market'
        crypto_id = _crypto_pairs[symbol]

        if not price:
            price = self.quote(symbol).ask

        stop_price = self._fprice(stop_price)
        price = self._fprice(price)
        account_id = self.portfolio()['account_id']

        payload = {
            "type": order,
            "side": side,
            "quantity": quantity,
            "account_id": account_id,
            "currency_pair_id": crypto_id,
            'price': price,
            'ref_id': uuid.uuid4().hex,
            "time_in_force": time_in_force,
            "trigger": trigger,
            'stop_price': stop_price
        }

        # payload must use json.dumps (unsure why)
        payload = {k:v for k,v in payload.items() if v}
        payload = dumps(payload)
        return self._req_post(crypto_endpoints.orders(), data=payload)

    ###########################################################################
    #                               CANCEL ORDER
    ###########################################################################

    def cancel(self, order):
        if 'cancel' in order:
            cancel_url = order['cancel']
        elif 'cancel_url' in order:
            cancel_url = order['cancel_url']
        else:
            raise Exception("Neither, 'cancel' nor 'cancel_url' were found")
        return self._req_post(cancel_url, asjson=False)
