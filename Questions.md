======= Questions =======

1. (Client) What is your risk profile? (See analysis of Jonas's plan) 
2. (Jonas) When do we consider data stale? How far back do we go?
3. (Jonas) What is actually an acceptable % vendor uncertainty? Can this be improved?

======= Analysis of Jonas's plan =======

Vendor fallback is practical but we must assess if we are confident with a 40% uncertainty "band_pct"
    I will still use the fallback for sites with missing Grid_Map data but will flag these organisations in the analysis of the output. If they appear in the top 5, they will be manually assessed against chronological entries with grid_map data

See it as a big risk to take the average - this is a risk the client needs to choose to take. Output will give the client a choice between:
    - Real data - ignore sites missing data - (Low risk: Risk of missing great sites with missing data points but certainty you are not exploring sites with missing data points that are poor)
    - Synthetic data - augment missing data with sythentic data & ignore missing data - (Medium risk: Risk that AI data points are wrong)
    - **Averages - Average data to score every site - (High risk/High reward: Chance that we spend money looking at sites that have missing data points and data was poor but also a chance for best-outcome sites)

** In real life, I would call a colleague, in this case Jonas, who is really good at statistical analysis and check if average, median, or re-weighting is more fair to sites. Assume averages for prototype

======= Assumptions =======

1. If no land registry entry (Error 404: Parcel not found), kill site (Conservative approach as it could be protected area)
2. Will automatically convert all Nordholm headroom from kW -> MW
3. Assume "band_pct" of 40% is within client risk tolerance but flag each of these entries where it is used and assess