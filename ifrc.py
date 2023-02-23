#!/usr/bin/python
"""
IFRC:
----

Reads IFRC data and creates datasets.

"""
import logging

from hdx.data.dataset import Dataset
from hdx.data.showcase import Showcase
from hdx.location.country import Country
from hdx.utilities.dateparse import parse_date
from hdx.utilities.dictandlist import dict_of_lists_add
from slugify import slugify

logger = logging.getLogger(__name__)


def flatten(data):
    new_data = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            new_data[key] = value
        else:
            for k, v in value.items():
                new_data[f"{key}.{k}"] = v
    return new_data


class IFRC:
    def __init__(self, configuration, retriever, last_run_date):
        self.configuration = configuration
        self.retriever = retriever
        self.base_url = self.configuration["base_url"]
        self.get_params = self.configuration["get_params"]
        self.last_run_date = last_run_date
        self.iso3_to_id = {}

    def download_data(self, url, basename, add_rows_fn):
        rows = []
        rows_by_country = {}
        qc_status_country = {}
        i = 0
        while url:
            filename = basename.format(index=i)
            json = self.retriever.download_json(url, filename=filename)
            for row in json["results"]:
                add_rows_fn(rows, rows_by_country, qc_status_country, row)
            url = json["next"]
            i += 1
        return rows, rows_by_country, qc_status_country

    def get_countries(self):
        dataset_info = self.configuration["countries"]
        country_path = dataset_info["url_path"]
        url = f"{self.base_url}{country_path}{self.get_params}"
        filename = dataset_info["filename"]

        def add_rows(rows, rows_by_country, qc_status_country, row):
            countryiso = row["iso3"]
            ifrc_id = row["id"]
            rows_by_country[countryiso] = ifrc_id

        _, self.iso3_to_id, _ = self.download_data(url, filename, add_rows_fn=add_rows)

    def get_appealdata(self):
        dataset_info = self.configuration["appeals"]
        appeal_path = dataset_info["url_path"]
        additional_params = dataset_info["additional_params"]
        url = f"{self.base_url}{appeal_path}{self.get_params}{additional_params}{self.last_run_date}T00:00:00"
        filename = dataset_info["filename"]
        qc_statuscode_country = {}

        def add_rows(rows, rows_by_country, qc_status_country, row):
            status = row["status"]
            if status == 3:  # Ignore Archived status
                return
            row["initial_num_beneficiaries"] = row["num_beneficiaries"]
            del row["num_beneficiaries"]
            row = flatten(row)
            countryiso = row["country.iso3"]
            row["country.name"] = Country.get_country_name_from_iso3(countryiso)
            rows.append(row)
            dict_of_lists_add(rows_by_country, countryiso, row)
            qc_status = qc_statuscode_country.get(countryiso, 100)
            if status < qc_status:
                qc_statuscode_country[countryiso] = status
                qc_status_country[countryiso] = row["status_display"]

        return self.download_data(url, filename, add_rows_fn=add_rows)

    def get_whowhatwheredata(self):
        dataset_info = self.configuration["whowhatwhere"]
        whowhatwhere_path = dataset_info["url_path"]
        url = f"{self.base_url}{whowhatwhere_path}{self.get_params}"
        filename = dataset_info["filename"]

        def add_rows(rows, rows_by_country, qc_status_country, row):
            countryiso = row["project_country_detail"]["iso3"]
            countryname = Country.get_country_name_from_iso3(countryiso)
            district_names = ", ".join(
                [d["name"] for d in row["project_districts_detail"]]
            )
            societyname = row["reporting_ns_detail"]["society_name"]
            primary_sector = row["primary_sector_display"]
            secondary_sectors = ", ".join(row["secondary_sectors_display"])
            programme_type = row["programme_type_display"]
            operation_type = row["operation_type_display"]
            status_display = row["status_display"]
            start_date = row["start_date"]
            end_date = row["end_date"]
            budget_amount = row["budget_amount"]
            actual_expenditure = row["actual_expenditure"]
            target_male = row["target_male"]
            target_female = row["target_female"]
            target_other = row["target_other"]
            target_total = row["target_total"]
            reached_male = row["reached_male"]
            reached_female = row["reached_female"]
            reached_other = row["reached_other"]
            reached_total = row["reached_total"]
            name = row["name"]
            row = {
                "country.iso3": countryiso,
                "country.name": countryname,
                "district.names": district_names,
                "country.society_name": societyname,
                "primary_sector": primary_sector,
                "secondary_sectors": secondary_sectors,
                "programme_type": programme_type,
                "operation_type": operation_type,
                "status_display": status_display,
                "start_date": start_date,
                "end_date": end_date,
                "budget_amount": budget_amount,
                "actual_expenditure": actual_expenditure,
                "target_male": target_male,
                "target_female": target_female,
                "target_other": target_other,
                "target_total": target_total,
                "reached_male": reached_male,
                "reached_female": reached_female,
                "reached_other": reached_other,
                "reached_total": reached_total,
                "name": name,
            }
            rows.append(row)
            dict_of_lists_add(rows_by_country, countryiso, row)
            qc_status = qc_status_country.get(countryiso)
            if qc_status is None or status_display == "Ongoing":
                qc_status_country[countryiso] = status_display

        return self.download_data(url, filename, add_rows_fn=add_rows)

    def generate_dataset_and_showcase(
        self,
        folder,
        rows,
        dataset_type,
        countryiso=None,
        global_dataset_url=None,
    ):
        """ """
        if rows is None:
            return None, None
        dataset_info = self.configuration[dataset_type]
        heading = dataset_info["heading"]
        global_name = f"Global IFRC {heading} Data"
        if countryiso is not None:
            rows = rows.get(countryiso)
            countryname = Country.get_country_name_from_iso3(countryiso)
            if countryname is None:
                logger.error(f"Unknown ISO 3 code {countryiso}!")
                return None, None
            title = f"{countryname} - IFRC {heading}"
            name = f"IFRC {heading} Data for {countryname}"
            filename = f"{heading.lower()}_data_{countryiso.lower()}.csv"
            notes = f"There is also a [global dataset]({global_dataset_url})."
        else:
            title = f"Global - IFRC {heading}"
            name = global_name
            filename = f"{heading.lower()}_data_global.csv"
            notes = (
                f"This data can also be found as individual country datasets on HDX."
            )

        logger.info(f"Creating dataset: {title}")
        slugified_name = slugify(name).lower()
        dataset = Dataset(
            {
                "name": slugified_name,
                "title": title,
                "notes": notes,
            }
        )
        dataset.set_maintainer("196196be-6037-4488-8b71-d786adf4c081")
        dataset.set_organization("3ada79f1-a239-4e09-bb2e-55743b7e6b69")
        dataset.set_expected_update_frequency("Every week")
        dataset.set_subnational(False)
        if countryiso:
            dataset.add_country_location(countryiso)
        else:
            dataset.add_other_location("world")

        tags = ["hxl"] + dataset_info["tags"]
        dataset.add_tags(tags)

        resourcedata = {
            "name": name,
            "description": f"IFRC {heading} data with HXL tags",
        }

        def process_date(row):
            start_date = parse_date(row["start_date"])
            end_date = parse_date(row["end_date"])
            society = row["country.society_name"]
            identifier = row.get("aid")
            if identifier:
                identifier = f"aid = {identifier}"
            else:
                identifier = f"country = {row['country.name']}"
            if end_date < start_date:
                logger.warning(f"End date < start date for {society} {identifier}")
                return None
            result = {}
            if start_date.year > 1900:
                result["startdate"] = start_date
            else:
                logger.warning(f"Start date year < 1900 for {society} {identifier}")
            if end_date.year > 1900:
                result["enddate"] = end_date
            else:
                logger.warning(f"End date year < 1900 for {society} {identifier}")
            return result

        success, results = dataset.generate_resource_from_iterator(
            list(rows[0].keys()),
            rows,
            dataset_info["hxltags"],
            folder,
            filename,
            resourcedata,
            date_function=process_date,
        )
        if success is False:
            logger.warning(f"{name} has no data!")
            return None, None

        showcase_urls = dataset_info["showcase_urls"]
        if countryiso:
            showcase_url = showcase_urls.get("country")
            if showcase_url:
                showcase_url = showcase_url.format(id=self.iso3_to_id[countryiso])
        else:
            showcase_url = showcase_urls.get("global")
        if showcase_url:
            showcase = Showcase(
                {
                    "name": f"{slugified_name}-showcase",
                    "title": f"{title} showcase",
                    "notes": f"IFRC Go Dashboard of {heading} Data",
                    "url": showcase_url,
                    "image_url": "https://avatars.githubusercontent.com/u/22204810?s=200&v=4",
                }
            )
            showcase.add_tags(tags)
        else:
            showcase = None
        return dataset, showcase
