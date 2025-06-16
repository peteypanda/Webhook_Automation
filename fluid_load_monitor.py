import requests
from requests_kerberos import HTTPKerberosAuth, OPTIONAL
from urllib3 import disable_warnings
import os
import subprocess
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from tabulate import tabulate
import json
import traceback
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            logging.info("Authenticated to FCLM portal")
        except Exception as e:
            logging.error(f"Failed to authenticate to FCLM portal: {e}")
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
            logging.info("Running mwinit for authentication...")
            subprocess.run(["mwinit"] + flags, check=True)

        with open(cookie, "rt") as c:
            cookie_file = c.readlines()

        cookies = {}
        now = time.time()
        for line in range(4, len(cookie_file)):
            if int(cookie_file[line].split("\t")[4]) < now:
                logging.info("Cookie expired, refreshing...")
                subprocess.run(["mwinit"] + flags, check=True)
                return self.mw_cookie(flags=flags)
            cookies[cookie_file[line].split("\t")[5]] = str.replace(
                cookie_file[line].split("\t")[6], "\n", ""
            )
        return cookies

    def get_html_data(self, process_id: str, start_time: str, end_time: str):
        params = {
            "warehouseId": self.fc,
            "spanType": "Intraday",
            "startDate": start_time,
            "endDate": end_time,
            "reportFormat": "HTML",
            "processId": process_id,
            "processPath": "RECEIVE"
        }

        try:
            response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup", params=params)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.error(f"Failed to fetch HTML data: {e}")
            return None


def parse_table(html_content, table_id):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'function-4300032947'})

    if not table:
        logging.warning(f"Table {table_id} not found in the response")
        return None

    columns = ['Login ID', 'Associate Name', 'Manager', 'Hours', 'Jobs', 'UPH']
    data = []

    for row in table.find_all('tr', class_='empl-all'):
        cells = row.find_all(['td', 'th'])
        if cells[0].text.strip().lower() == 'total':
            continue

        if len(cells) >= 22:
            try:
                case_uph = cells[22].text.strip()
                case_uph_value = float(case_uph) if case_uph else 0
                if case_uph_value >= 190:
                    continue
            except ValueError:
                case_uph_value = 0

            paid_hours = cells[8].text.strip()
            jph = cells[10].text.strip()
            name = ' '.join(word.capitalize() for word in cells[2].text.strip().split(',')[::-1])
            manager = ' '.join(word.capitalize() for word in cells[3].text.strip().split(',')[::-1])

            row_data = [
                cells[1].text.strip(),
                name,
                manager,
                f"{float(paid_hours):.2f}" if paid_hours and paid_hours != '-' else '-',
                cells[9].text.strip(),
                f"{float(case_uph):.2f}" if case_uph and case_uph != '-' else '-'
            ]

            row_data = ['-' if not cell else cell for cell in row_data]
            if any(cell != '-' for cell in row_data):
                data.append(row_data)

    return columns, data


def get_time_range():
    now = datetime.now()
    end_time = now.replace(minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(hours=1)
    return start_time.strftime("%Y-%m-%dT%H:%M:%S.000"), end_time.strftime("%Y-%m-%dT%H:%M:%S.000")


def send_slack_message(workflow_url, title, metrics, footer):
    payload = {
        "title": title,
        "metrics": metrics,
        "footer": footer
    }
    try:
        response = requests.post(workflow_url, json=payload)
        response.raise_for_status()
        logging.info("Slack notification sent successfully")
    except Exception as e:
        logging.error(f"Failed to send Slack notification: {e}")


def normal_run(fclm, workflow_url, process_id, table_id):
    sent_hours_today = set()  # Track hours sent today
    last_date = None  # Track date changes

    while True:
        try:
            now = datetime.now()
            current_date = now.date()
            current_hour = now.hour
            
            # Reset sent hours on new day
            if last_date != current_date:
                sent_hours_today.clear()
                last_date = current_date
                logging.info(f"New day detected: {current_date}. Clearing sent hours tracker.")
            
            # Create unique hour identifier with date and hour
            hour_id = f"{current_date}_{current_hour}"
            
            # Only process if we haven't sent for this hour today
            if hour_id not in sent_hours_today:
                logging.info(f"[⏰ {now.strftime('%Y-%m-%d %H:%M:%S')}] Fetching Fluid Load data for hour {current_hour} (first time today)...")

                start_time, end_time = get_time_range()
                html_content = fclm.get_html_data(process_id, start_time, end_time)

                if html_content:
                    result = parse_table(html_content, table_id)
                    if result:
                        headers, data = result
                        if data:
                            logging.info(f"Found {len(data)} associates below 190 UPH")
                            logging.info(tabulate(data, headers=headers, tablefmt='fancy_grid'))

                            table_str = tabulate(data, headers=headers, tablefmt='pipe')
                            title = f"PSC2 Low UPH Alert - {len(data)} Associates Below 190 UPH"
                            metrics = f"```\nAssociates Below 190 UPH Case:\n\n{table_str}\n```"
                            footer = f"Time Range: {start_time} to {end_time}"
                            send_slack_message(workflow_url, title, metrics, footer)
                        else:
                            logging.info("✅ All associates above 190 UPH.")
                            send_slack_message(
                                workflow_url,
                                "PSC2 UPH Status - All Clear",
                                "All associates are at or above 190 UPH Case",
                                f"Time Range: {start_time} to {end_time}"
                            )
                    else:
                        logging.warning("No table data parsed.")
                else:
                    logging.warning("No HTML content retrieved.")

                # Mark this hour as sent
                sent_hours_today.add(hour_id)
                logging.info(f"Completed processing for hour {current_hour}. Added to sent tracker.")
                
            elif current_hour != getattr(normal_run, 'last_logged_hour', None):
                logging.info(f"Hour {current_hour} already processed today - skipping")
                normal_run.last_logged_hour = current_hour

            # Sleep 1 min then loop again
            time.sleep(60)

        except KeyboardInterrupt:
            logging.info("Interrupted by user.")
            break
        except Exception as e:
            logging.error(f"❌ Error occurred: {e}")
            traceback.print_exc()
            time.sleep(300)


def main():
    # HARDCODED VALUES - No user input needed
    fc = "PSC2"
    process_id = "01003021"
    table_id = "4300032947"
    workflow_url = "https://hooks.slack.com/triggers/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"

    logging.info("🚀 Starting automated Fluid Load monitoring for PSC2...")
    
    # NO STARTUP NOTIFICATION - Only send hourly metrics during scheduled times
    
    fclm = FCLM(fc)
    
    try:
        normal_run(fclm, workflow_url, process_id, table_id)
    except Exception as e:
        logging.error(f"Unhandled error: {e}")
        traceback.print_exc()
        
        # Send error notification
        try:
            send_slack_message(
                workflow_url,
                "❌ Fluid Load Monitor Error",
                f"Error occurred in Fluid Load Monitor:\n```\n{str(e)}\n```",
                "Monitor may need attention"
            )
        except:
            pass


if __name__ == "__main__":
    main()