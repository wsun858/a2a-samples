from mcp.server.fastmcp import FastMCP

from currency_service import CurrencyService

mcp = FastMCP("Currency Exchange Server")

currency_service = CurrencyService()

@mcp.tool()
def get_exchange_rate(currency_from: str = 'USD', currency_to: str = 'EUR', currency_date: str = 'latest') -> dict:
    """
    Get the exchange rate between two currencies using the Frankfurter API.
    :param currency_from: The currency to convert from (e.g., "USD")
    :param currency_to: The currency to convert to (e.g., "EUR")
    :param currency_date: The date for the exchange rate or "latest"
    :return: a dictionary containing the exchange rate data
    """
    print(f"Fetching exchange rate from {currency_from} to {currency_to} for date {currency_date}")
    return currency_service.get_exchange_rate(currency_from, currency_to, currency_date)

if __name__ == "__main__":
    # a = get_exchange_rate()
    # print(a)
    mcp.run(transport="stdio")