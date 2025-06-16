import sys
import pandas as pd
import pendulum
import requests
from requests_kerberos import HTTPKerberosAuth, OPTIONAL
from urllib3 import disable_warnings
import os
import subprocess
import time
from bs4 import BeautifulSoup
from tabulate import tabulate
import json
import traceback
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Universal column index map for all tables
STANDARD_INDEX_MAP = {
    'SidelineApp Each Total': 19,
    'SidelineApp Tote Unit': 21,
    'EachReceived Each Total': 33,
    'EachReceived Job Unit': 35,
    'LPReceived Each Total': 47,
    'LPReceived Case Unit': 49,
    'CubiscannedItem Each Total': 63,
    'ItemPrepped Each Total': 77,
    'ItemPrepped Job Unit': 79,
    'Paid Hours': 8
}

def safe_extract(cells, index, default=0):
    try:
        return float(cells[index].text.strip() or default)
    except (IndexError, ValueError):
        return default

def build_dynamic_row(cells, employee_id, name, index_map):
    row_data = {
        'Employee ID': employee_id,
        'Name': name,
    }
    for key, idx in index_map.items():
        if idx < len(cells):
            val = safe_extract(cells, idx)
            row_data[key] = val
    if 'Paid Hours' in index_map and index_map['Paid Hours'] < len(cells):
        paid_hours = safe_extract(cells, index_map['Paid Hours'])
        row_data['Paid Hours'] = paid_hours
    else:
        row_data['Paid Hours'] = 0
    row_data['Grand Total'] = sum(
        v for k, v in row_data.items() if k not in ['Employee ID', 'Name', 'Paid Hours']
    )
    row_data['Rate'] = row_data['Grand Total'] / row_data['Paid Hours'] if row_data['Paid Hours'] > 0 else 0
    return row_data

class FCLM:
    def __init__(self, fc: str):
        disable_warnings()
        self.fc = fc.upper()
        self.authenticate()

    def authenticate(self):
        self.cookie = self.mw_cookie()
        self.session = requests.Session()
        self.session.cookies.update(self.cookie)
        self.session.auth = HTTPKerberosAuth(mutual_authentication=OPTIONAL)
        self.session.verify = False

        try:
            response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup")
            if response.status_code != 200:
                self.reset_mw_cookie()
                self.session.cookies.update(self.cookie)
                response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup")
            print("Authenticated to FCLM portal")
        except Exception as e:
            print(f"Failed to authenticate to FCLM portal: {e}")
            raise

    def reset_mw_cookie(self, flags: list = None):
        self.cookie = self.mw_cookie(flags=flags, delete_cookie=True)
        self.session.cookies.update(self.cookie)

    def mw_cookie(self, flags=None, delete_cookie: bool = False):
        if flags is None:
            flags = ["-o", "--aea"]
        path = os.path.join(os.path.expanduser("~"), ".midway")
        cookie = os.path.join(path, "cookie")

        if delete_cookie and os.path.exists(cookie):
            os.remove(cookie)

        if not os.path.exists(cookie):
            print("Running mwinit for authentication...")
            subprocess.run(["mwinit"] + flags, check=True)

        with open(cookie, "rt") as c:
            cookie_file = c.readlines()

        cookies = {}
        now = time.time()
        for line in range(4, len(cookie_file)):
            if int(cookie_file[line].split("\t")[4]) < now:
                print("Cookie expired, refreshing...")
                subprocess.run(["mwinit"] + flags, check=True)
                return self.mw_cookie(flags=flags)
            cookies[cookie_file[line].split("\t")[5]] = str.replace(
                cookie_file[line].split("\t")[6], "\n", ""
            )
        return cookies

    def get_html_data(self, process_id: str, start_time: pendulum.DateTime, end_time: pendulum.DateTime):
        params = {
            "warehouseId": self.fc,
            "spanType": "Intraday",
            "processId": process_id,
            "startDateIntraday": start_time.strftime("%Y/%m/%d"),
            "endDateIntraday": end_time.strftime("%Y/%m/%d"),
            "startHourIntraday": start_time.hour,
            "startMinuteIntraday": start_time.minute,
            "endHourIntraday": end_time.hour,
            "endMinuteIntraday": end_time.minute,
            "maxIntradayDays": 2
        }
        logging.info(f"Fetching data for process_id: {process_id}")
        logging.info(f"Parameters: {params}")

        try:
            response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup", params=params)
            response.raise_for_status()
            logging.info(f"Successfully fetched data. Response length: {len(response.text)}")
            return response.text
        except Exception as e:
            logging.error(f"Failed to fetch HTML data: {e}")
            return None

def parse_receive_html_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': lambda x: x and x.startswith('function-4300006787')})
    if not table:
        logging.warning("Table not found in HTML content for Receive ProblemSolve")
        return None

    data = []
    for row in table.find_all('tr', class_='empl-all'):
        cells = row.find_all('td')
        if len(cells) >= 3:
            employee_id = cells[1].text.strip()
            name = cells[2].text.strip()
            if name and not name.replace(',', '').replace('.', '').isdigit():
                row_data = build_dynamic_row(cells, employee_id, name, STANDARD_INDEX_MAP)
                data.append(row_data)

    if not data:
        logging.warning("No valid data found for Receive ProblemSolve")
        return None

    df = pd.DataFrame(data)
    df = df.sort_values('Rate', ascending=False)
    df['Grand Total'] = df['Grand Total'].round(0)
    df['Paid Hours'] = df['Paid Hours'].round(2)
    df['Rate'] = df['Rate'].round(2)
    result_columns = ['Employee ID', 'Name', 'Grand Total', 'Paid Hours', 'Rate']
    return df[result_columns]

def parse_stow_psolve_html_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'function-4300035067'})
    if not table:
        logging.warning("Table not found in HTML content for Stow Psolve Backlog")
        return None

    data = []
    for row in table.find_all('tr', class_='empl-all'):
        cells = row.find_all('td')
        if len(cells) >= 3:
            employee_id = cells[1].text.strip()
            name = cells[2].text.strip()
            if name and not name.replace(',', '').replace('.', '').isdigit():
                row_data = build_dynamic_row(cells, employee_id, name, STANDARD_INDEX_MAP)
                data.append(row_data)

    if not data:
        logging.warning("No valid data found for Stow Psolve Backlog")
        return None
    df = pd.DataFrame(data)
    df = df.sort_values('Rate', ascending=False)
    df['Grand Total'] = df['Grand Total'].round(0)
    df['Paid Hours'] = df['Paid Hours'].round(2)
    df['Rate'] = df['Rate'].round(2)
    result_columns = ['Employee ID', 'Name', 'Grand Total', 'Paid Hours', 'Rate']
    return df[result_columns]

def parse_rc_sort_psolve_html_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'function-4300006776'})
    if not table:
        logging.warning("Table not found in HTML content for RC Sort ProblemSolve")
        return None

    data = []
    for row in table.find_all('tr', class_='empl-all'):
        cells = row.find_all('td')
        if len(cells) >= 3:
            employee_id = cells[1].text.strip()
            name = cells[2].text.strip()
            if name and not name.replace(',', '').replace('.', '').isdigit():
                row_data = build_dynamic_row(cells, employee_id, name, STANDARD_INDEX_MAP)
                data.append(row_data)

    if not data:
        logging.warning("No valid data found for RC Sort ProblemSolve")
        return None
    df = pd.DataFrame(data)
    df = df.sort_values('Rate', ascending=False)
    df['Grand Total'] = df['Grand Total'].round(0)
    df['Paid Hours'] = df['Paid Hours'].round(2)
    df['Rate'] = df['Rate'].round(2)
    result_columns = ['Employee ID', 'Name', 'Grand Total', 'Paid Hours', 'Rate']
    return df[result_columns]

def parse_outbound_html_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'function-4300006849'})
    if not table:
        logging.warning("Table not found in HTML content for TransferOut PSolve")
        return None

    data = []
    for row in table.find_all('tr', class_='empl-all'):
        cells = row.find_all('td')
        if len(cells) >= 3:
            employee_id = cells[1].text.strip()
            name = cells[2].text.strip()
            if name and not name.replace(',', '').replace('.', '').isdigit():
                row_data = build_dynamic_row(cells, employee_id, name, STANDARD_INDEX_MAP)
                data.append(row_data)

    if not data:
        logging.warning("No valid data found for TransferOut PSolve")
        return None

    df = pd.DataFrame(data)
    df = df.sort_values('Rate', ascending=False)
    df['Grand Total'] = df['Grand Total'].round(0)
    df['Paid Hours'] = df['Paid Hours'].round(2)
    df['Rate'] = df['Rate'].round(2)
    result_columns = ['Employee ID', 'Name', 'Grand Total', 'Paid Hours', 'Rate']
    return df[result_columns]

def send_slack_message(workflow_url, title, metrics, footer):
    data = {
        "title": title,
        "metrics": metrics,
        "footer": footer,
    }
    headers = {"Content-Type": "application/json"}
    print("Payload to be sent:")
    print(json.dumps(data, indent=2))
    resp = requests.post(workflow_url, json=data, headers=headers)
    print(f"Data sent to workflow. Response status code: {resp.status_code}")

def get_quarters():
    return [
        ("Quarter 1 Days", (7, 30), (9, 30)),
        ("Quarter 2 Days", (9, 45), (11, 45)),
        ("Quarter 3 Days", (12, 15), (15, 0)),
        ("Quarter 4 Days", (15, 15), (17, 30)),
        ("Quarter 1 Nights", (18, 30), (21, 0)),
        ("Quarter 2 Nights", (21, 15), (23, 15)),
        ("Quarter 3 Nights", (23, 45), (2, 30)),
        ("Quarter 4 Nights", (2, 45), (5, 0))
    ]

def get_current_quarter(now):
    quarters = get_quarters()
    for quarter, start, end in quarters:
        start_time = now.replace(hour=start[0], minute=start[1])
        end_time = now.replace(hour=end[0], minute=end[1])
        if start[0] > end[0]:
            if now.hour < end[0] or (now.hour == end[0] and now.minute <= end[1]):
                start_time = start_time.subtract(days=1)
            else:
                end_time = end_time.add(days=1)
        if start_time <= now < end_time:
            return quarter, start_time, end_time
    return None, None, None

def run_quarter(fclm, workflow_url, quarter, start_time, end_time):
    logging.info(f"Processing {quarter} from {start_time} to {end_time}")

    if end_time < start_time:
        end_time = end_time.add(days=1)

    try:
        metrics = ""

        # Receive ProblemSolve
        receive_html = fclm.get_html_data("1002980", start_time, end_time)
        if receive_html:
            receive_rates = parse_receive_html_data(receive_html)
            if receive_rates is not None and not receive_rates.empty:
                receive_table = tabulate(
                    receive_rates, headers='keys', tablefmt='pipe', showindex=False,
                    numalign='right', stralign='left', floatfmt=(".0f", "", ".0f", ".2f", ".2f")
                )
                metrics += f"🟦 **Receive ProblemSolve Rates**\n```\n{receive_table}\n```\n\n"
            else:
                metrics += "🟦 **Receive ProblemSolve Rates:** No valid data.\n\n"

        # Stow Psolve Backlog
        stow_html = fclm.get_html_data("01002980", start_time, end_time)
        if stow_html:
            stow_rates = parse_stow_psolve_html_data(stow_html)
            if stow_rates is not None and not stow_rates.empty:
                stow_table = tabulate(
                    stow_rates, headers='keys', tablefmt='pipe', showindex=False,
                    numalign='right', stralign='left', floatfmt=(".0f", "", ".0f", ".2f", ".2f")
                )
                metrics += f"🟧 **Stow Psolve Backlog Rates**\n```\n{stow_table}\n```\n\n"
            else:
                metrics += "🟧 **Stow Psolve Backlog Rates:** No valid data.\n\n"

        # RC Sort & TransferOut PSolve (BOTH from processId 1003018, different tables)
        psolve_html = fclm.get_html_data("1003018", start_time, end_time)
        if psolve_html:
            # RC Sort ProblemSolve (yellow)
            rc_sort_rates = parse_rc_sort_psolve_html_data(psolve_html)
            if rc_sort_rates is not None and not rc_sort_rates.empty:
                rc_sort_table = tabulate(
                    rc_sort_rates, headers='keys', tablefmt='pipe', showindex=False,
                    numalign='right', stralign='left', floatfmt=(".0f", "", ".0f", ".2f", ".2f")
                )
                metrics += f"🟨 **RC Sort ProblemSolve Rates**\n```\n{rc_sort_table}\n```\n\n"
            else:
                metrics += "🟨 **RC Sort ProblemSolve Rates:** No valid data.\n\n"

            # TransferOut PSolve (green)
            transferout_rates = parse_outbound_html_data(psolve_html)
            if transferout_rates is not None and not transferout_rates.empty:
                transferout_table = tabulate(
                    transferout_rates, headers='keys', tablefmt='pipe', showindex=False,
                    numalign='right', stralign='left', floatfmt=(".0f", "", ".0f", ".2f", ".2f")
                )
                metrics += f"🟩 **TransferOut PSolve Rates**\n```\n{transferout_table}\n```\n\n"
            else:
                metrics += "🟩 **TransferOut PSolve Rates:** No valid data.\n\n"

        title = f"PSC2 {quarter} Problem Solve Rates"
        footer = f"Created by pucpetey for PSC2\nTime Range: {start_time.format('YYYY-MM-DD HH:mm')} to {end_time.format('YYYY-MM-DD HH:mm')}"

        if metrics.strip():
            send_slack_message(workflow_url, title, metrics.strip(), footer)
            logging.info("Slack message sent successfully")
        else:
            logging.warning(f"No data available for {quarter}")
            send_slack_message(workflow_url, title, f"No data available for {quarter}", footer)
            logging.info("Slack message sent (no data available)")

    except Exception as e:
        error_message = f"Error processing {quarter}: {str(e)}"
        logging.error(error_message)
        logging.error(traceback.format_exc())
        send_slack_message(workflow_url, "Error in Problem Solve Rates Script", f"```\n{error_message}\n```", "An error occurred while processing data")
        logging.info("Slack message sent (error notification)")

def normal_run(fclm, workflow_url):
    # Track quarters sent today to prevent duplicates on restart
    quarters_sent_today = set()
    last_notification_date = None
    
    while True:
        now = pendulum.now('America/Los_Angeles')
        current_date = now.date()
        
        # Reset quarters sent tracker on new day
        if last_notification_date != current_date:
            quarters_sent_today.clear()
            last_notification_date = current_date
            logging.info(f"New day detected: {current_date}. Clearing quarters sent tracker.")
        
        current_quarter, start_time, end_time = get_current_quarter(now)

        if current_quarter is None:
            time.sleep(30)
            continue

        if end_time < start_time:
            end_time = end_time.add(days=1)

        # Create unique quarter identifier with date and quarter name
        quarter_id = f"{current_date}_{current_quarter}"
        
        time_to_wait = (end_time - now) + pendulum.duration(minutes=1)
        if time_to_wait.total_seconds() > 0:
            logging.info(f"Waiting {time_to_wait.total_seconds()} seconds until 1 minute after {current_quarter} ends")
            time.sleep(time_to_wait.total_seconds())

        # Only send if we haven't sent for this quarter today
        if quarter_id not in quarters_sent_today:
            logging.info(f"Processing {current_quarter} for {current_date} (first time today)")
            run_quarter(fclm, workflow_url, current_quarter, start_time, end_time)
            quarters_sent_today.add(quarter_id)
            logging.info(f"Completed {current_quarter}. Added to sent tracker.")
        else:
            logging.info(f"Quarter {current_quarter} for {current_date} already processed today - skipping")

        time.sleep(10)

def main():
    # HARDCODED VALUES - No user input needed
    fc = "PSC2"
    workflow_url = "https://hooks.slack.com/triggers/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"
    
    logging.info("🚀 Starting WorkingRate in automated normal mode for PSC2")
    
    # Send startup notification
    try:
        send_slack_message(
            workflow_url, 
            "🚀 WorkingRate Monitor Started", 
            "Automated Problem Solve Rates monitoring started for PSC2\nRunning in normal mode - will send reports at end of each quarter",
            "Auto-started by token monitor"
        )
    except Exception as e:
        logging.error(f"Failed to send startup notification: {e}")
    
    fclm = FCLM(fc)
    
    # AUTOMATICALLY RUN IN NORMAL MODE - No user choice needed
    logging.info("Running in automated normal mode. Monitoring quarters...")
    try:
        normal_run(fclm, workflow_url)
    except KeyboardInterrupt:
        logging.info("Normal mode interrupted.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    main()