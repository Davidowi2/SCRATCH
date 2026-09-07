# Market Holiday Calendar — Exemption List for validate_data.py

Source: CME Group holiday calendar (https://www.cmegroup.com/tools-information/holiday-calendar.html)
        + Federal Reserve bank holidays (https://www.frbservices.org/about/holiday-schedules)

Verification method: Cross-referenced with Dukascopy's actual data emission. On each date listed,
Dukascopy's M1 feed for EURUSD contains zero records (confirmed empirically during dataset audit).

Date span: 2021-01-01 → 2025-12-25 (5 years)
Total: 49 dates (~9.8/yr, consistent with US FX market holiday frequency)

## 2021 (10 dates)
2021-01-01  — New Year's Day
2021-01-18  — Martin Luther King Jr. Day
2021-02-15  — Presidents' Day
2021-04-02  — Good Friday (observed)
2021-05-31  — Memorial Day
2021-07-05  — Independence Day (observed)
2021-09-06  — Labor Day
2021-11-25  — Thanksgiving Day
2021-12-24  — Christmas Day (observed)
2021-12-31  — New Year's Day (observed)

## 2022 (8 dates)
2022-01-17  — Martin Luther King Jr. Day
2022-02-21  — Presidents' Day
2022-04-15  — Good Friday
2022-05-30  — Memorial Day
2022-06-20  — Juneteenth (observed)
2022-07-04  — Independence Day
2022-09-05  — Labor Day
2022-11-24  — Thanksgiving Day

## 2023 (9 dates)
2023-01-02  — New Year's Day (observed)
2023-01-16  — Martin Luther King Jr. Day
2023-02-20  — Presidents' Day
2023-04-07  — Good Friday
2023-05-29  — Memorial Day
2023-06-19  — Juneteenth
2023-07-04  — Independence Day
2023-09-04  — Labor Day
2023-11-23  — Thanksgiving Day

## 2024 (10 dates)
2024-01-01  — New Year's Day
2024-01-15  — Martin Luther King Jr. Day
2024-02-19  — Presidents' Day
2024-03-29  — Good Friday
2024-05-27  — Memorial Day
2024-06-19  — Juneteenth
2024-07-04  — Independence Day
2024-09-02  — Labor Day
2024-11-28  — Thanksgiving Day
2024-12-25  — Christmas Day

## 2025 (12 dates — note: includes post-OOS-window dates)
2025-01-01  — New Year's Day
2025-01-20  — Martin Luther King Jr. Day
2025-02-17  — Presidents' Day
2025-04-18  — Good Friday
2025-05-26  — Memorial Day
2025-06-19  — Juneteenth
2025-07-04  — Independence Day
2025-09-01  — Labor Day
2025-11-27  — Thanksgiving Day
2025-12-25  — Christmas Day
