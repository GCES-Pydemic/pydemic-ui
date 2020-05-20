__package__ = "pydemic_ui.ui"

import os

import streamlit as st
import pandas as pd
from babel.dates import format_date

from pydemic.utils import fmt, pc
from .. import info
from ..components import (
    cards,
    info_component,
    md_description,
    footnote_disclaimer,
    html,
    main_component,
)
from ..i18n import _, __

#
# Messages
#
NO_ICU_MESSAGE = __(
    """
The location does not have any ICU beds. At peak demand, it needs to reserve {n}
beds from neighboring cities.
"""
)

ICU_OVERFLOW_MESSAGE = __(
    """
The location will **run out of ICU beds at {date}**. At peak demand, it will need **{n}
new ICUs**. This demand corresponds to **{surge} times** the number of beds dedicated
to COVID-19 and {total} of the total number of ICU beds.
"""
)

GOOD_CAPACITY_MESSAGE = __(
    """
The number of ICU beds is sufficient for the expected demand in this scenario.
"""
)

EQUIPMENT_MESSAGE = __(
    """
The table bellow show the recommended usage of PPE by healthcare workers
during the period of simulation.
"""
)


@main_component()
def summary_cards(model):
    """
    Show list of summary cards for the results of simulation.
    """

    def datum(x):
        return f"{fmt(int(x))} ({pc(x / population)})"

    region = model.region
    disease = model.disease
    results = model.results

    deaths = results["deaths"]
    hospitalizations = results["hospitalized_cases"]
    extra_icu = model["icu_overflow:max"]
    extra_hospitals = model["hospital_overflow:max"]
    recovered = results["recovered"]
    population = model.population

    # Print friendlier messages if region has no ICU or hospital beds
    if model.icu_capacity > 0:
        icu_overflow_date = results["dates.icu_overflow"]
    else:
        icu_overflow_date = _("No ICU beds!")
    if model.hospital_capacity > 0:
        hospital_overflow_date = results["dates.hospital_overflow"]
    else:
        hospital_overflow_date = _("No hospital beds!")

    # A peak of cases in the final date is bogus: it probably corresponds
    # to a simulation that simply did not run long enough to see the peak
    peak_cases = model["infectious:peak-date"]
    if peak_cases == model.date:
        peak_cases = _("Still coming...")

    # Do not reference Brasil io as a data source :(
    brasil_io = '<a href="http://brasil.io" target="_blank">Brasil.io</a>'
    cases_title = _("Confirmed cases*").format(link=brasil_io)
    deaths_title = _("Confirmed deaths*").format(link=brasil_io)
    cards(
        {
            cases_title: fmt(info.get_confirmed_cases_for_region(region, disease)),
            deaths_title: fmt(info.get_confirmed_deaths_for_region(region, disease)),
        },
        escape=False,
        color="st-red",
    )
    html('<div style="height: 0.5rem;"></div>')
    cards(
        {
            _("Deaths"): datum(deaths),
            _("Hospitalizations"): datum(hospitalizations),
            _("Required extra ICU beds"): fmt(extra_icu),
            _("Required extra hospital beds"): fmt(extra_hospitals),
            _("No more ICU beds available by"): natural_date(icu_overflow_date),
            _("No more hospital beds available by"): natural_date(hospital_overflow_date),
            _("Estimated date for the peak"): natural_date(peak_cases),
            _("Cumulative attack rate"): pc(recovered / population),
        }
    )
    st.markdown(_("&ast; Compiled from local Healthcare Secretaries"))


@info_component("main")
def healthcare_parameters(
    icu_capacity,
    hospital_capacity,
    icu_full_capacity,
    icu_overflow_date,
    extra_icu,
    where=st,
):
    """
    Write base healthcare parameters.
    """
    where.header(_("Healthcare system"))

    md_description(
        {
            _("COVID/SARI ICUs"): fmt(int(icu_capacity)),
            _("COVID/SARI hospital beds"): fmt(int(hospital_capacity)),
        },
        where=where,
    )

    if icu_full_capacity == 0:
        msg = NO_ICU_MESSAGE.format(n=fmt(extra_icu))
    elif icu_overflow_date:
        peak_icu = extra_icu + icu_capacity
        msg = ICU_OVERFLOW_MESSAGE.format(
            date=natural_date(icu_overflow_date),
            n=fmt(int(peak_icu - icu_capacity)),
            surge=fmt(peak_icu / icu_capacity),
            total=fmt(peak_icu / icu_full_capacity),
        )
    else:
        msg = str(GOOD_CAPACITY_MESSAGE)

    where.markdown(msg)


@main_component()
def epidemiological_parameters(model):
    """
    Basic report with epidemiological parameters.
    """

    days = model.iter
    mortality = model["deaths:final:pp"]
    fatality = model["empirical-CFR:final"]
    infected = model["infected:final:pp"]

    st.header(_("Advanced epidemiological information"))
    mortality *= 100_000
    mortality = fmt(mortality)
    fatality = pc(fatality)
    infected = pc(infected)
    symptomatic = pc(model.prob_symptoms)

    md_description(
        {
            _("Number of cases generated by a single case"): fmt(model.R0),
            _("Mortality (deaths per 100k population)"): mortality,
            _("Letality ({pc} of deaths among the ill)").format(pc="%"): fatality.rstrip(
                "%"
            ),
        }
    )
    lang = os.environ.get("LANGUAGE", "en_US")
    footnote_disclaimer(**locals())


@main_component()
def ppe_demand(model):
    """
    A simple table with the required personal protection equipment demand.
    """

    # TODO: add source
    st.header(_("Personal protection equipment"))
    st.markdown(str(EQUIPMENT_MESSAGE))

    h_days = model["severe"].sum()
    i_days = model["critical"].sum()
    table = healthcare_equipment_resources(h_days, i_days)
    table.iloc[:, -1] = table.iloc[:, -1].apply(fmt)
    st.table(table)

    # Legend explaining M, B, etc
    clean = lambda st: "".join(c for c in st if c.isalpha())
    letters = set(table.iloc[:, -1].apply(clean))

    lines = []
    if "M" in letters:
        lines.append(_("M = million"))
    if "B" in letters:
        lines.append(_("B = billion"))
    if lines:
        data = ", ".join(lines)
        html(f'<div style="font-size: smaller; text-align: right">* {data}</div>')


def healthcare_equipment_resources(hospital_days, icu_days):
    """
    Return the recommended usage of protection equipment by healthcare staff
    from the number of hospitalization x days and ICU x days.
    """

    columns = [_("Quantity"), _("Total")]
    tuples = zip([_("Patients/day"), ""], columns)

    N = int(hospital_days + icu_days)
    a = 1  # / 5
    b = 1  # / 15
    df = pd.DataFrame(
        [
            [_("Cirurgical masks"), 25, 25 * N],
            [_("N95 mask"), a, a * N],
            [_("Waterproof apron"), 25, 25 * N],
            [_("Non-sterile glove"), 50, 50 * N],
            [_("Faceshield"), b, b * N],
        ]
    ).set_index(0)

    df.index.name = _("Name")
    df.columns = pd.MultiIndex.from_tuples(tuples)
    return df


def natural_date(x):
    """
    Friendly representation of dates.

    String inputs are returned as-is.
    """
    if isinstance(x, str):
        return x
    elif x is None:
        return _("Not soon...")
    else:
        return format_date(x, format="short")


if __name__ == "__main__":
    from ..examples import seir
    from pydemic_ui import st

    st.css()
    m = seir()
    summary_cards(m)
    ppe_demand(m)
    epidemiological_parameters(m)
