from .Order import Order, CryptoOrder

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

    def _req_get(self, *args, timeout=15, **kwargs):
        res = self.session.get(*args, timeout=timeout, **kwargs)
        res.raise_for_status()
        return res

    def _req_get_json(self, *args, timeout=15, **kwargs):
        return self._req_get(*args, timeout=timeout, **kwargs).json()

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
        return self._req_get_json(endpoints.fundamentals(symbol.upper()))

    def instrument(self, symbol):
        """Fetch instrument info"""
        url = str(endpoints.instruments()) + "?symbol=" + str(symbol)
        results = self._req_get_json(url)['results'][0]
        return results if results else Exception(f"Invalid symbol: {symbol}")

    def quote(self, symbol):
        """Fetch stock quote"""
        symbol = symbol.upper()
        crypto_symbol = symbol + 'USD'
        if crypto_symbol in _crypto_pairs:
            url = str(crypto_endpoints.quotes(_crypto_pairs[crypto_symbol]))
            return self._req_get_json(url)

        url = str(endpoints.quotes()) + f"?symbols={symbol}"
        return self._req_get_json(url)['results'][0]

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
        return self._req_get_json(url)['results'][0]

    ###########################################################################
    #                               Account Data
    ###########################################################################

    def account(self):
        res = self._req_get_json(endpoints.accounts())
        return res['results'][0]

    def crypto_account(self):
        res = self._req_get_json(crypto_endpoints.accounts())
        return res['results'][0]

    def portfolios(self):
        return self._req_get_json(endpoints.portfolios())['results']

    def orders(self):
        return self._req_get_json(endpoints.orders())['results']

    def order(self, order:[dict, str]):
        order_id = order['id'] if isinstance(order, dict) else order
        return self._req_get_json(endpoints.orders() + order_id)

    def crypto_orders(self):
        return self._req_get_json(crypto_endpoints.orders())['results']

    def crypto_order(self, order):
        order_id = order['id'] if isinstance(order, dict) else order
        return self._req_get_json(crypto_endpoints.orders() + order_id)

    def dividends(self):
        return self._req_get_json(endpoints.orders())

    def positions(self):
        return self._req_get_json(endpoints.positions())

    ###########################################################################
    #                               PLACE ORDER
    ###########################################################################
    def buy(self,
            symbol,
            quantity,
            price=None,
            stop_price=None,
            time_in_force=None):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns:
            Response object
        """
        return self.place_order(symbol=symbol,
                                quantity=quantity,
                                price=price,
                                side='buy',
                                stop_price=stop_price,
                                time_in_force=time_in_force)

    def sell(self,
             symbol,
             quantity,
             price=None,
             stop_price=None,
             time_in_force=None):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns:
            Response object
        """
        return self.place_order(symbol=symbol,
                                quantity=quantity,
                                price=price,
                                side='sell',
                                stop_price=stop_price,
                                time_in_force=time_in_force)

    def place_order(self,
                    symbol,
                    quantity,
                    side,
                    price=None,
                    stop_price=None,
                    time_in_force=None):
        """
        Args:
            symbol: the stock symbol
            quantity: number of shares
            price: the limit price, if None defaults to a market order
            stop_price: the stop-loss price, if None defaults to an immediate (regular) order
            time_in_force: 'gfd' or 'gtc', gfd: cancel end of day, gtc: cancel until specified

        Returns:
            Response object
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
            side,
            time_in_force)

        return order_type(self, json_result)

    def _place_order_detail(
            self, instrument, quantity, price, stop_price, side, time_in_force):

        trigger = 'stop' if stop_price else 'immediate'
        order = 'limit' if price else 'market'
        price = price if price else self.quote(instrument['symbol'])['ask_price']

        payload = {
            "account": self.account()["url"],
            "instrument": unquote(instrument["url"]),
            "symbol": instrument["symbol"],
            "quantity": quantity,
            "side": side,
            "type": order.lower(),
            "trigger": trigger,
            "time_in_force": time_in_force,
            "extended_hours": 'false',
            'price': price,
            'stop_price': stop_price
        }
        print(payload)

        res = self.session.post(endpoints.orders(), data=payload, timeout=15)
        res.raise_for_status()
        return res.json()

    def _place_crypto_order_detail(
            self, symbol, quantity, price, stop_price, side, time_in_force):

        trigger = 'stop' if stop_price else 'immediate'
        order = 'limit' if price else 'market'
        crypto_id = _crypto_pairs[symbol]

        if price is None:
            price = self._req_get_json(crypto_endpoints.quotes(crypto_id))['ask_price']

        # Crypto trades requires price be formatted to two decimal places
        if price is not None: price = float(price)
        price = "{0:.2f}".format(price)

        if stop_price is not None: stop_price = float(stop_price)
        json = self._req_get_json(crypto_endpoints.portfolios())
        account_id = json['results'][0]['account_id']

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

        # Crypto trades must have content-type application/json only
        content_type = self.session.headers['Content-Type']
        self.session.headers['Content-Type'] = 'application/json'

        # payload must use json.dumps (unsure why)
        payload = dumps(payload)
        res = self.session.post(crypto_endpoints.orders(), data=payload, timeout=15)

        # Restore original content-type
        self.session.headers['Content-Type'] = content_type

        res.raise_for_status()
        return res.json()

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
        res = self.session.post(cancel_url, timeout=15)
        res.raise_for_status()
        return res
