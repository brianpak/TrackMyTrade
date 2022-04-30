import sys, os, requests, configparser, datetime, pytz, time, calendar, json, csv

def GET(config, end_point, params = ''):
    api_version     = 'v1/'
    api_server      = config['api_server']
    access_token    = config['access_token']
    token_type      = config['token_type']
    headers         = { 'Authorization': token_type + ' ' + access_token }

    response = requests.get(api_server + api_version + end_point, headers = headers, params = params)
    return response

def get_account_id(config):
    response = GET(config, 'accounts/')

    if response.status_code != 200:
        msg = f'Error code: {response.status_code}, Error message: {response.content}.'
        sys.exit(msg)

    data = response.json()
    margin_account = None

    for account in data['accounts']:
        if account['type'] == 'Margin':
            margin_account = account

    if margin_account:
        return margin_account['number']
    else:
        sys.exit('Margin account not found')

def import_fx_rates(year, month):
    filename = f'fx_rate/{year}/{month}.csv'

    fx_rates = {}
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                day = int(row['Day'])
                rate = float(row['Rate'])

                fx_rates[day] = rate
        return fx_rates
    except:
        sys.exit(filename + ' not found.')
    

def extract_trade_days(fx_rates):
    dict_keys = fx_rates.keys()
    trade_days = list(dict_keys)
    trade_days.sort()
    
    return trade_days


def format_dates(year, month, day):
    dates = {}

    start_time = datetime.datetime(year, month, day)
    end_time = start_time + datetime.timedelta(seconds= 1)

    # Watch out timezones: EST = -05:00 and EDT = -04:00

    dates['start_time'] = start_time.strftime('%Y-%m-%dT%H:%M:%S-05:00')
    dates['end_time'] = end_time.strftime('%Y-%m-%dT%H:%M:%S-05:00')

    return dates

def get_activities(config, account_id, year, month, day):
    dates = format_dates(year, month, day)
    params = { 'startTime': dates['start_time'], 'endTime': dates['end_time'] }

    response = GET(config, f'accounts/{account_id}/activities', params)
    if response.status_code != 200:
        msg = f'Error code: {response.status_code}, Error message: {response.content}.'
        sys.exit(msg)

    data = response.json()
    return data

def filter_trades(data):
    activities = data['activities']
    return [activity for activity in activities if activity['type'] == 'Trades']

def process_trades(trades):
    processed_trades = []
    for trade in trades:
        processed_trade = {}

        trade_date      = trade["tradeDate"]
        datetime_obj = datetime.datetime.strptime(trade_date, '%Y-%m-%dT%H:%M:%S.%f%z')

        processed_trade['Ticker']       = trade["symbol"]
        processed_trade['Shares']       = trade["quantity"]
        processed_trade['Date']         = datetime_obj.strftime('%Y-%m-%d')
        processed_trade['Action']       = trade["action"]
        processed_trade['Price']        = trade['price']
        processed_trade['Gross Price']  = trade['grossAmount']
        processed_trade['Commission']   = trade['commission']
        processed_trade['Net Amount']   = trade['netAmount']
        processed_trade['Currency']     = trade['currency']
        processed_trade['Curr Rate']    = ''

        processed_trades.append(processed_trade)
    return processed_trades

def inject_fx_rate(trades, fx_rate):
    for trade in trades:
        if (trade['Currency'] == 'USD'):
            trade['Curr Rate'] = fx_rate
        
        elif (trade['Currency'] == 'CAD'):
            trade['Curr Rate'] = 1

def is_complement_trades(trade1, trade2):
    if trade1['Ticker'] != trade2['Ticker']:
        return False

    if trade1['Action'] == trade2['Action']:
        return False

    return True

def is_conversion_trades(trade1, trade2):
    ticker1 = trade1['Ticker']
    ticker2 = trade2['Ticker']

    if (ticker1 != 'DLR.TO' and ticker2 != 'DLR.U.TO') and (ticker1 != 'DLR.U.TO' and ticker2 != 'DLR.TO'):
        return False
    
    if trade1['Action'] == trade2['Action']:
        return False

    return True

def arrange_intraday_trades(trades, open_trades, closed_trades):
    count = len(trades)

    i = 0
    while i < count:
        trade1 = trades[i]

        # not the last elem
        if i < count - 1: 
            trade2 = trades[i + 1]

            if is_complement_trades(trade1, trade2):
                closed_trades.append((trade1, trade2))

                # move to next index
                i += 1

            else:
                open_trades.append(trade1)

        # last elem
        else:
            open_trades.append(trade1)

        i += 1

def arrange_interday_trades(open_trades, closed_trades):
    count = len(open_trades)

    i = 0
    while i < count:
        trade1 = open_trades[i]

        j = i + 1
        while j < count:
            trade2 = open_trades[j]

            if is_complement_trades(trade1, trade2):
                closed_trades.append((trade1, trade2))
                
                open_trades.pop(j)  # remove the 2nd trade of the closed trade
                open_trades.pop(i)  # remove the 1st trade of the closed trade

                # move to previous index
                i -= 1

                # correct count
                count -= 2

                break

            j += 1

        i += 1



def filter_conversion_trades(open_trades, conversion_trades):
    count = len(open_trades)

    i = 0
    while i < count:
        trade1 = open_trades[i]

        # not the last elem
        if i < count - 1: 
            trade2 = open_trades[i + 1]

            if is_conversion_trades(trade1, trade2):
                conversion_trades.append((trade1, trade2))

                # remove the conversion trades (i and i + 1)
                del open_trades[i : i + 1 + 1]

                # move to previous index
                i -= 1

                # correct count
                count -= 2

        # handle last elem (unclosed trade)

        i += 1


def sort_trades(merged_trades):
    merged_trades.sort(key = lambda trade: datetime.datetime.strptime(trade['2 Date'], '%Y-%m-%d'))

def merge_regular_trades(closed_trades, merged_trades):
    for trades in closed_trades:
        trade1 = trades[0]
        trade2 = trades[1]

        merged_trade = {}
        merge_trades(merged_trade, trade1, trade2)

        # calculate P&L
        pnl_usd = trade1['Net Amount'] + trade2['Net Amount']
        pnl_cad = (trade1['Net Amount'] + trade2['Net Amount']) * trade2['Curr Rate']

        merged_trade["P&L USD"] = round(pnl_usd, 2)
        merged_trade["P&L CAD"] = round(pnl_cad, 2)

        merged_trades.append(merged_trade)

def merge_conversion_trades(conversion_trades, merged_trades):
    for trades in conversion_trades:
        trade1 = trades[0]
        trade2 = trades[1]

        merged_trade = {}
        merge_trades(merged_trade, trade1, trade2)

        pnl_cad = 0

        # calculate P&L
        if trade1['Currency'] == 'CAD' and trade2['Currency'] == 'USD':
            pnl_cad = trade1['Net Amount'] + trade2['Net Amount'] * trade2['Curr Rate']

        elif trade1['Currency'] == 'USD' and trade2['Currency'] == 'CAD':
            pnl_cad = trade1['Net Amount'] * (1 / trade2['Curr Rate']) + trade2['Net Amount']

        merged_trade["P&L USD"] = 0
        merged_trade["P&L CAD"] = round(pnl_cad, 2)

        merged_trades.append(merged_trade)

def merge_trades(merged_trade, trade1, trade2):
    # append "1 " to all keys in trade1
    for key in trade1.keys():
        newKey = f'1 {key}'
        value = trade1[key]

        merged_trade[newKey] = value

    # append "2 " to all keys in trade2
    for key in trade2.keys():
        newKey = f'2 {key}'
        value = trade2[key]

        merged_trade[newKey] = value

def calculate_daily_pnl(merged_trades):
    sum_usd = 0
    sum_cad = 0

    previous_date = ""
    for merged_trade in merged_trades:
        current_date = merged_trade["2 Date"]

        if previous_date != current_date:
            sum_usd = 0
            sum_cad = 0

        pnl_usd = merged_trade["P&L USD"]
        pnl_cad = merged_trade["P&L CAD"]

        sum_usd += pnl_usd
        sum_cad += pnl_cad

        merged_trade["Daily SUM USD"] = round(sum_usd, 2)
        merged_trade["Daily SUM CAD"] = round(sum_cad, 2)

        previous_date = current_date


def export_data(year, month, merged_trades):
    filename = f'output/{year}/{month}.csv'

    try:
        with open(filename, mode='w', newline='') as csv_file:
            fieldnames = field_names()
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            for merged_trade in merged_trades:
                writer.writerow(merged_trade)

    except:
        sys.exit(filename + ' not found.')

def field_names():
    return [
        '1 Ticker', '1 Shares', '1 Date', '1 Action', '1 Price', '1 Gross Price', '1 Commission', '1 Net Amount', '1 Currency', '1 Curr Rate',
        '2 Ticker', '2 Shares', '2 Date', '2 Action', '2 Price', '2 Gross Price', '2 Commission', '2 Net Amount', '2 Currency', '2 Curr Rate',
        'P&L USD', 'P&L CAD', 'Daily SUM USD', 'Daily SUM CAD'
    ]

def grab_data(config):
    account_id = get_account_id(config)

    year = int(input("Enter year: "))
    month = int(input("Enter month: "))

    fx_rates = import_fx_rates(year, month)
    trade_days = extract_trade_days(fx_rates)
    
    open_trades = []
    closed_trades = []

    print("Watch out timezones: EST = -05:00 and EDT = -04:00")

    for trade_day in trade_days:
        data = get_activities(config, account_id, year, month, trade_day)
        if data:
            trades = filter_trades(data)
            trades = process_trades(trades)
            
            fx_rate = fx_rates[trade_day]
            inject_fx_rate(trades, fx_rate)
            
            arrange_intraday_trades(trades, open_trades, closed_trades)

        time.sleep(0.1)

    merged_trades = []
    merge_regular_trades(closed_trades, merged_trades)

    # move conversion trades out of open trades
    conversion_trades = []
    filter_conversion_trades(open_trades, conversion_trades)
    merge_conversion_trades(conversion_trades, merged_trades)

    # move interday trades out of open trades
    closed_trades = []
    arrange_interday_trades(open_trades, closed_trades)
    merge_regular_trades(closed_trades, merged_trades)
    
    sort_trades(merged_trades)

    calculate_daily_pnl(merged_trades)

    export_data(year, month, merged_trades)

def main():
    config = read_config()
    grab_data(config)

def read_config():
    cp = configparser.ConfigParser()
    cp.read('config.txt')

    config = {}

    value = cp.get('DEFAULT', 'api_server')
    if not value:
        sys.exit('api_server is not provided in the config file')
    config['api_server'] = value

    value = cp.get('DEFAULT', 'access_token')
    if not value:
        sys.exit('access_token is not provided in the config file')
    config['access_token'] = value

    value = cp.get('DEFAULT', 'token_type')
    if not value:
        sys.exit('token_type is not provided in the config file')
    config['token_type'] = value

    return config

if __name__ == "__main__":
    main()