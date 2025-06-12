import httpx

class CurrencyService:
    def get_exchange_rate(
        self,  # Add self parameter
        currency_from: str = 'USD',
        currency_to: str = 'EUR',
        currency_date: str = 'latest',
    ):
        """Use this to get current exchange rate.

        Args:
            currency_from: The currency to convert from (e.g., "USD").
            currency_to: The currency to convert to (e.g., "EUR").
            currency_date: The date for the exchange rate or "latest". Defaults to
                "latest".

        Returns:
            A dictionary containing the exchange rate data, or an error message if
            the request fails.
        """
        try:
            response = httpx.get(
                f'https://api.frankfurter.app/{currency_date}',
                params={'from': currency_from, 'to': currency_to},
            )
            response.raise_for_status()

            data = response.json()
            if 'rates' not in data:
                return {'error': 'Invalid API response format.'}
            return data
        except httpx.HTTPError as e:
            return {'error': f'API request failed: {e}'}
        except ValueError:
            return {'error': 'Invalid JSON response from API.'}