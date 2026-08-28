# Appendix C - Parameters and sources

**Generated from the model's own configuration files**, so the values cannot drift from what the model reads.

A source is shown against a parameter only where that parameter's own entry in the configuration names one; citations are deliberately not spread from a parameter to its neighbours, since a block routinely mixes measured quantities with design choices. Where no source applies, the cell states the category instead: *switch* (turns a mechanism on or off), *shares sum to 1* (exhaustive by construction), *model structure* (the study's own resolution and periods), *derived* (computed from a sourced parameter, derivation in the configuration and Appendices B and D), *bound* (a cap the optimiser may not exceed), *label*, and *design choice* (a decision this study makes and argues in Chapters 3 and 4, such as the site, the 25 km² area, the design population and the height tiers).


## Coverage

| configuration file | parameters tabulated |
|---|---|
| `config/demographics.yaml` | 20 |
| `config/demand_norms.yaml` | 70 |
| `config/district_composition.yaml` | 146 |
| `config/climate.yaml` | 158 |
| `config/economics.yaml` | 1027 |
| `config/price_trajectories.yaml` | 9 |
| total | 1430 |

437 of 1430 rows name a source, 411 of them as a direct link. The rest are structural: switches that turn a technology on or off, shares that sum to one, the model's own time and space resolution, and quantities derived arithmetically from a sourced parameter above them. Full provenance for every block, including the derivations, is kept in the configuration comments.


---

## Population and income structure

`config/demographics.yaml`


### Population

| parameter | value | units | source |
|:---|:---|:---|:---|
| `population.total` | 250000 | persons | [nhm.gov.in](https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf) |

### Income shares


All keys below sit under `income_shares`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ews` | 0.20 | - | [weforum.org](https://www.weforum.org/reports/the-future-of-consumption-in-fast-growth-consumer-markets/) |
| `lig` | 0.20 | - | [pmay-urban.gov.in](https://pmay-urban.gov.in/uploads/guidelines/Operational-Guidelines-of-PMAY-U.pdf%29:) |
| `mig` | 0.45 | - | [pmay-urban.gov.in](https://pmay-urban.gov.in/uploads/guidelines/Operational-Guidelines-of-PMAY-U.pdf%29:) |
| `hig` | 0.15 | - | [pmay-urban.gov.in](https://pmay-urban.gov.in/uploads/guidelines/Operational-Guidelines-of-PMAY-U.pdf%29:) |

### Household size by income


All keys below sit under `household_size_by_income`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ews` | 5.0 | - | [mospi.gov.in](https://www.mospi.gov.in/sites/default/files/reports_and_publication/NSS78-20-21/Table1-Estimated-persons-and-households.xlsx) |
| `lig` | 4.8 | - | *design choice* |
| `mig` | 4.5 | - | *design choice* |
| `hig` | 4.2 | - | *design choice* |

### Age structure


All keys below sit under `age_structure`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `under_18` | 0.30 | - | [censusindia.gov.in](https://censusindia.gov.in/nada/index.php/catalog/1464) |
| `age_18_to_64` | 0.62 | - | [censusindia.gov.in](https://censusindia.gov.in/nada/index.php/catalog/1464) |
| `over_65` | 0.08 | - | [censusindia.gov.in](https://censusindia.gov.in/nada/index.php/catalog/1464) |

### (root)

| parameter | value | units | source |
|:---|:---|:---|:---|
| `worker_share_of_population` | 0.36 | persons | [censusindia.gov.in](https://censusindia.gov.in/nada/index.php/catalog/1464) |
| `school_enrolment_rate` | 0.92 | - | NSSO |

### Employment mix


All keys below sit under `employment_mix`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `professional_office` | 0.28 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |
| `services_retail` | 0.30 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |
| `industry` | 0.16 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |
| `healthcare` | 0.05 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |
| `public_services` | 0.05 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |
| `informal` | 0.16 | - | [marketmystique.com](https://marketmystique.com/it-companies-in-mohali/) |

---

## Demand norms and end uses

`config/demand_norms.yaml`


### Education


All keys below sit under `education`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `population_per_primary_school` | 5000 | persons | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `population_per_secondary_school` | 7500 | persons | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `floor_m2_per_primary_school` | 2500 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `floor_m2_per_secondary_school` | 5000 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `students_per_primary_school` | 1500 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `students_per_senior_secondary` | 1500 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `primary_share_of_enrolled` | 0.55 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `secondary_share_of_enrolled` | 0.45 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Healthcare


All keys below sit under `healthcare`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `population_per_uphc` | 50000 | persons | IPHS |
| `population_per_uchc` | 275000 | persons | IPHS |
| `floor_m2_per_uphc` | 1500 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `floor_m2_per_uchc` | 24000 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `beds_per_1000_population` | 3.0 | per 1,000 | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `beds_per_dispensary` | 10 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `beds_per_hospital` | 100 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `dispensary_share_of_beds` | 0.30 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `hospital_share_of_beds` | 0.70 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Retail


All keys below sit under `retail`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `m2_per_capita` | 4.0 | per person | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `share_in_shopping_centre` | 0.50 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `share_in_highstreet` | 0.20 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `m2_per_restaurant_seat` | 2.5 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `restaurant_seats_per_1000_pop` | 60 | per 1,000 | [restaurantindia.in](https://www.restaurantindia.in/article/india-to-be-the-3rd-largest-food-service-market-by-2028-overtaking-japan-nrai-ifsr-2024) |

### Office

| parameter | value | units | source |
|:---|:---|:---|:---|
| `office.m2_per_professional_worker` | 10.0 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `office.m2_per_public_services_worker` | 12.0 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Parking


All keys below sit under `parking`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ecs_per_100m2_by_use.high_income_residential` | 0.25 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.mid_income_residential` | 0.10 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.low_income_residential` | 0.05 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.office` | 1.8 | ECS | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s35f4f78111ff6538d1f5ea498032c4745/uploads/2025/03/20250310296203399.pdf) |
| `ecs_per_100m2_by_use.shopping_centre` | 3.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.light_industry` | 2.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.warehouse_cold_storage` | 3.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.healthcare` | 2.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.public_services` | 1.8 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.hotel_guesthouse` | 3.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.school` | 2.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.retail_highstreet` | 2.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.religious` | 2.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `ecs_per_100m2_by_use.restaurant_food_service` | 3.0 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `m2_per_ecs` | 23 | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `lot_net_to_gross` | 0.85 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `car_ownership_total_by_income` | 2030: {low: 0.02, mid: 0.15, high: 0.45}; 2042: {low: 0.05, mid: 0.25, high: 0.50}; 2055: {low: 0.10, mid: 0.40, high: 0.55} | - | [dataforindia.com](https://www.dataforindia.com/vehicle-ownership/) |
| `onplot_ecs_per_dwelling` | 1.0 | ECS | *design choice* |
| `external_commuter_share` | 0.15 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `worker_ecs_uses` | [office, light_industry, warehouse_cold_storage, public_services] | ECS | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `peak_away_share` | 0.40 | - | [cseindia.org](https://www.cseindia.org/parking-restraint-must-to-reduce-car-usage-and-promote-clean-commuting-practices-says-cse-analysis-6131) |
| `visitor_peak_share` | 0.12 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `occupancy_profiles.office` | [0.02, 0.02, 0.02, 0.05, 0.55, 0.95, 0.90, 0.95, 0.80, 0.35, 0.10, 0.03] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.shopping_centre` | [0.05, 0.02, 0.02, 0.05, 0.15, 0.40, 0.60, 0.65, 0.70, 0.90, 0.85, 0.30] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.light_industry` | [0.15, 0.15, 0.15, 0.30, 0.80, 0.85, 0.85, 0.85, 0.75, 0.45, 0.20, 0.15] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.warehouse_cold_storage` | [0.20, 0.20, 0.20, 0.35, 0.75, 0.80, 0.80, 0.80, 0.70, 0.45, 0.25, 0.20] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.healthcare` | [0.20, 0.15, 0.15, 0.25, 0.60, 0.90, 0.85, 0.80, 0.70, 0.55, 0.35, 0.25] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.public_services` | [0.02, 0.02, 0.02, 0.05, 0.50, 0.90, 0.85, 0.90, 0.70, 0.25, 0.05, 0.02] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.hotel_guesthouse` | [0.90, 0.90, 0.90, 0.85, 0.60, 0.45, 0.45, 0.50, 0.60, 0.75, 0.85, 0.90] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `occupancy_profiles.high_income_residential` | [0.90, 0.90, 0.90, 0.85, 0.55, 0.35, 0.35, 0.40, 0.55, 0.80, 0.90, 0.90] | - | [uli.org](https://www.uli.org/wp-content/uploads/ULI-Documents/Shared-Parking.pdf) |
| `lot_net_to_gross_effective` | 0.70 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `canopy_fraction_of_cell` | 0.35 | - | *shares sum to 1* |

### Industry

| parameter | value | units | source |
|:---|:---|:---|:---|
| `industry.m2_per_industrial_worker` | 30.0 | m² | *design choice* |
| `industry.warehouse_m2_per_industrial_worker` | 8.0 | m² | *switch* |

### Hospitality

| parameter | value | units | source |
|:---|:---|:---|:---|
| `hospitality.hotel_rooms_per_1000_pop` | 11 | per 1,000 | [hotelivate.com](https://www.hotelivate.com/travel-tourism/sizing-up-indian-hospitality/) |
| `hospitality.m2_per_hotel_room` | 35.0 | m² | *design choice* |

### Open space

| parameter | value | units | source |
|:---|:---|:---|:---|
| `open_space.m2_per_capita_total` | 12.0 | per person | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Blue space

| parameter | value | units | source |
|:---|:---|:---|:---|
| `blue_space.m2_per_capita_total` | 4.0 | per person | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Religious

| parameter | value | units | source |
|:---|:---|:---|:---|
| `religious.m2_per_capita` | 0.4 | per person | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### Solar

| parameter | value | units | source |
|:---|:---|:---|:---|
| `solar.target_kwp_per_capita` | 0.8 | per person | *bound* |
| `solar.ground_mount_kwp_per_m2` | 0.08022 | kWp | *design choice* |

### Public services


All keys below sit under `public_services`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `water_treatment_kwh_per_capita_per_year` | 25.9 | kWh/cap/yr | [cpheeo.gov.in](http://cpheeo.gov.in) |
| `street_lighting_kwh_per_capita_per_year` | 10 | kWh/cap/yr | [esmap.org](https://www.esmap.org/sites/esmap.org/files/DocumentLibrary/India%20EE%20Street%20Lighting%20Implementation%20and%20Financing%20%28P149482%29%20June%2027%202015_Optimized.pdf) |
| `street_lighting_class_weights.weights.arterial` | 2.0 | - | [law.resource.org](https://law.resource.org/pub/in/bis/S05/is.1944.1-2.1970.pdf) |
| `street_lighting_class_weights.weights.collector` | 1.0 | - | [law.resource.org](https://law.resource.org/pub/in/bis/S05/is.1944.1-2.1970.pdf) |
| `street_lighting_class_weights.weights.local` | 0.5 | - | [law.resource.org](https://law.resource.org/pub/in/bis/S05/is.1944.1-2.1970.pdf) |

---

## Land use, built form and ownership

`config/district_composition.yaml`


### Constraint catchments m


All keys below sit under `constraint_catchments_m`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `school` | 1000.0 | m | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `religious` | 800.0 | m | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `cool_refuge` | 1000.0 | m | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `healthcare` | 2500.0 | m | IPHS |
| `park` | 600.0 | m | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |

### (root)

| parameter | value | units | source |
|:---|:---|:---|:---|
| `park_cells_per_quadrant_min` | 4 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `floor_to_floor_m` | 3.0 | m | *design choice* |
| `rooftop_module_efficiency` | 0.1930 | - | *derived* |

### Lifetime demand trajectory


All keys below sit under `lifetime_demand_trajectory`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `population_growth.cagr_2030_2040` | 0.0045 | /yr | [statisticstimes.com](https://statisticstimes.com/demographics/india/punjab-population.php) |
| `population_growth.cagr_2040_2055` | 0.0035 | /yr | [statisticstimes.com](https://statisticstimes.com/demographics/india/punjab-population.php) |
| `population_growth.lifetime_avg_multiplier` | 1.05 | - | [statisticstimes.com](https://statisticstimes.com/demographics/india/punjab-population.php) |
| `ev_adoption_ramp.share_2030` | 0.05 | - | *design choice* |
| `ev_adoption_ramp.share_2055` | 0.15 | - | *design choice* |
| `ev_adoption_ramp.lifetime_avg_multiplier` | 1.0 | - | *derived* |
| `climate_drift_cooling.delta_t_2030_c` | 0.0 | - | IPCC; AR6 |
| `climate_drift_cooling.delta_t_2055_c` | 1.2 | - | [journals.plos.org](https://journals.plos.org/climate/article?id=10.1371/journal.pclm.0000724) |
| `climate_drift_cooling.cooling_elasticity_per_c` | 0.10 | - | [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC4523835/) |
| `climate_drift_cooling.cooling_share_of_demand` | 0.25 | - | IPCC; AR6 |
| `climate_drift_cooling.lifetime_avg_multiplier` | 1.015 | - | IPCC; AR6 |
| `cooking_electrification.share_2030` | 0.103 | - | [ceew.in](https://www.ceew.in/sites/default/files/ceew-study-on-clean-electric-cooking-transition-in-indian-homes.pdf) |
| `cooking_electrification.share_2055` | 0.30 | - | [ceew.in](https://www.ceew.in/sites/default/files/ceew-study-on-clean-electric-cooking-transition-in-indian-homes.pdf) |
| `cooking_electrification.cooking_share_of_residential_kwh` | 0.20 | - | [ceew.in](https://www.ceew.in/sites/default/files/ceew-study-on-clean-electric-cooking-transition-in-indian-homes.pdf) |
| `cooking_electrification.lifetime_avg_multiplier` | 1.0197 | - | [ceew.in](https://www.ceew.in/sites/default/files/ceew-study-on-clean-electric-cooking-transition-in-indian-homes.pdf) |
| `income_mobility.share_low_2030` | 0.40 | - | *design choice* |
| `income_mobility.share_mid_2030` | 0.45 | - | *design choice* |
| `income_mobility.share_high_2030` | 0.15 | - | *design choice* |
| `income_mobility.share_low_2055` | 0.28 | - | [bain.com](https://www.bain.com/insights/how-india-will-consume-in-2030-10-mega-trends/) |
| `income_mobility.share_mid_2055` | 0.52 | - | *design choice* |
| `income_mobility.share_high_2055` | 0.20 | - | *design choice* |
| `income_mobility.kwh_per_hh_low_2030` | 2204 | kWh | *design choice* |
| `income_mobility.kwh_per_hh_mid_2030` | 5796 | kWh | *design choice* |
| `income_mobility.kwh_per_hh_high_2030` | 12453 | kWh | *design choice* |
| `income_mobility.lifetime_avg_multiplier` | 1.0713 | - | *derived* |
| `ai_demand_uplift.office_industry_uplift_2030` | 0.05 | - | [iea.org](https://www.iea.org/reports/electricity-2024) |
| `ai_demand_uplift.office_industry_uplift_2055` | 0.20 | - | [iea.org](https://www.iea.org/reports/electricity-2024) |
| `ai_demand_uplift.office_industry_share_of_district_demand` | 0.10 | - | [iea.org](https://www.iea.org/reports/electricity-2024) |
| `ai_demand_uplift.multiplier_by_period` | 2030: 1.0000; 2042: 1.0069; 2055: 1.0143 | - | [iea.org](https://www.iea.org/reports/electricity-2024) |
| `ai_demand_uplift.lifetime_avg_multiplier` | 1.012 | - | [iea.org](https://www.iea.org/reports/electricity-2024) |
| `water_energy.baseline_dynamic_head_m` | 30 | m | [cgwb.gov.in](https://www.cgwb.gov.in/en/dynamic-ground-water-resources-india) |
| `water_energy.water_table_decline_m_per_year` | 0.26 | /yr | [india.mongabay.com](https://india.mongabay.com/2022/06/accelerating-rate-of-groundwater-depletion-in-punjab-worries-farmers-and-experts/) |
| `water_energy.pumping_share_of_water_energy` | 0.65 | - | [cgwb.gov.in](https://www.cgwb.gov.in/en/dynamic-ground-water-resources-india) |
| `water_energy.incremental_harvest_offset_by_period` | {2030: 0.00, 2042: 0.06, 2055: 0.13} | - | [cgwb.gov.in](https://www.cgwb.gov.in/en/dynamic-ground-water-resources-india) |
| `water_energy.water_share_of_district_demand` | 0.0078 | - | [cgwb.gov.in](https://www.cgwb.gov.in/en/dynamic-ground-water-resources-india) |
| `water_energy.multiplier_by_period` | 2030: 1.0000; 2042: 1.0000; 2055: 0.9999 | - | [cgwb.gov.in](https://www.cgwb.gov.in/en/dynamic-ground-water-resources-india) |

### Site


All keys below sit under `site`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `name` | Zirakpur-class peri-urban district (notional) | - | *label* |
| `latitude` | 30.64 | deg N | *design choice* |
| `longitude` | 76.82 | deg E | *design choice* |
| `target_year` | 2030 | year | *model structure* |
| `total_population` | 250000 | persons | *design choice* |
| `total_households` | 54346 | households | [nhm.gov.in](https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf%29) |
| `area_km2` | 25 | km² | MoSPI; NSS |
| `grid_n_rows` | 50 | cells | *model structure* |
| `grid_n_cols` | 50 | cells | *model structure* |
| `cell_size_m` | 100 | m | *design choice* |
| `prevailing_wind_summer` | NW | - | *design choice* |
| `prevailing_wind_winter` | NW | - | *design choice* |

### Land use targets


All keys below sit under `land_use_targets`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `residential_low` | 0.018 | - | *switch* |
| `residential_mid` | 0.050 | - | *switch* |
| `residential_high` | 0.090 | - | *switch* |
| `school` | 0.034 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `office` | 0.0036 | - | *switch* |
| `shopping_centre` | 0.007 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `retail_highstreet` | 0.003 | - | *switch* |
| `restaurant_food_service` | 0.0016 | - | *switch* |
| `hotel_guesthouse` | 0.0016 | - | *switch* |
| `healthcare` | 0.0036 | - | IPHS; URDPFI |
| `light_industry` | 0.014 | - | *switch* |
| `warehouse_cold_storage` | 0.006 | - | *switch* |
| `public_services` | 0.004 | - | *switch* |
| `religious` | 0.010 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `parking_lot` | 0.007 | - | *switch* |
| `open_space` | 0.3956 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `blue_space` | 0.040 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `road` | 0.231 | - | *switch* |
| `solar_farm` | 0.080 | - | *switch* |

### Income shares


All keys below sit under `income_shares`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low` | 0.40 | - | *shares sum to 1* |
| `mid` | 0.45 | - | *shares sum to 1* |
| `high` | 0.15 | - | *shares sum to 1* |

### Household floor area m2


All keys below sit under `household_floor_area_m2`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low` | 42.7 | m² | [anarock.com](https://www.anarock.com) |
| `mid` | 100 | m² | [anarock.com](https://www.anarock.com) |
| `high` | 300 | m² | [anarock.com](https://www.anarock.com) |

### Height tiers


All keys below sit under `height_tiers`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ground` | 7.0 | - | *design choice* |
| `short` | 12.0 | - | *design choice* |
| `medium` | 18.0 | - | *design choice* |
| `tall` | 27.0 | - | *design choice* |

### Height multipliers


All keys below sit under `height_multipliers`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ground` | 0.45 | - | *derived* |
| `short` | 0.67 | - | *derived* |
| `medium` | 1.00 | - | *derived* |
| `tall` | 1.50 | - | *derived* |

### Floor area per cell m2


All keys below sit under `floor_area_per_cell_m2`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential` | 20000 | m² | *design choice* |
| `mid_income_residential` | 20000 | m² | *design choice* |
| `high_income_residential` | 12000 | m² | *design choice* |
| `school` | 3500 | m² | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `office` | 30000 | m² | *design choice* |
| `shopping_centre` | 30000 | m² | *design choice* |
| `retail_highstreet` | 30000 | m² | *design choice* |
| `restaurant_food_service` | 10000 | m² | *design choice* |
| `hotel_guesthouse` | 30000 | m² | *design choice* |
| `healthcare` | 3600 | m² | IPHS |
| `light_industry` | 12500 | m² | *design choice* |
| `warehouse_cold_storage` | 8000 | m² | *switch* |
| `public_services` | 6000 | m² | *design choice* |
| `religious` | 4000 | m² | *design choice* |

### Pv acceptance


All keys below sit under `pv_acceptance`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential` | 0.70 | - | *design choice* |
| `mid_income_residential` | 0.45 | - | *design choice* |
| `high_income_residential` | 0.70 | - | *design choice* |
| `school` | 0.85 | - | *design choice* |
| `office` | 0.80 | - | *design choice* |
| `shopping_centre` | 0.85 | - | *design choice* |
| `retail_highstreet` | 0.60 | - | *design choice* |
| `restaurant_food_service` | 0.55 | - | *design choice* |
| `hotel_guesthouse` | 0.55 | - | *design choice* |
| `healthcare` | 0.55 | - | *design choice* |
| `light_industry` | 0.85 | - | *design choice* |
| `warehouse_cold_storage` | 0.90 | - | *switch* |
| `public_services` | 0.75 | - | *design choice* |
| `religious` | 0.0 | - | *design choice* |

### Building ownership


All keys below sit under `building_ownership`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential` | gov | - | *design choice* |
| `mid_income_residential` | rwa | - | *design choice* |
| `high_income_residential` | private | - | *design choice* |
| `school` | gov | - | *design choice* |
| `public_services` | gov | - | *design choice* |
| `healthcare` | gov | - | *design choice* |
| `office` | private | - | *design choice* |
| `shopping_centre` | private | - | *design choice* |
| `retail_highstreet` | private | - | *design choice* |
| `restaurant_food_service` | private | - | *design choice* |
| `hotel_guesthouse` | private | - | *design choice* |
| `light_industry` | private | - | *design choice* |
| `warehouse_cold_storage` | private | - | *switch* |
| `religious` | trust | - | *design choice* |

### Permeability


All keys below sit under `permeability`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `pedestrian` | all_cells | - | *design choice* |
| `bicycle` | all_cells | - | *design choice* |
| `vehicle` | road_only | - | *design choice* |
| `hv_cable` | road_only | - | *design choice* |
| `lv_cable` | all_cells | - | *design choice* |

### Optimisation


All keys below sit under `optimisation`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `initial_seed_archetype` | chandigarh_sector | - | *model structure* |
| `sector_size_cells` | 8 | - | [chandigarh.gov.in](https://chandigarh.gov.in/departments/chandigarh-master-plan-2031%29) |
| `n_iterations` | 15000 | - | *design choice* |
| `initial_temperature` | 0.08 | - | *design choice* |
| `final_temperature` | 0.0008 | - | *design choice* |
| `hard_penalty` | 40.0 | - | *design choice* |
| `soft_penalty` | 2.0 | - | *design choice* |
| `constraint_penalty_weight` | 2.0 | - | *design choice* |
| `rng_seed` | 42 | - | *model structure* |
| `log_every` | 250 | - | *design choice* |

---

## Climate and irradiance

`config/climate.yaml`


### Climate


All keys below sit under `climate`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `jan.t_mean_c` | 12.7 | - | IMD |
| `jan.t_max_c` | 18.2 | - | IMD |
| `jan.t_min_c` | 7.2 | - | IMD |
| `jan.rh14_pct` | 47 | % | IMD |
| `jan.rainfall_mm` | 37.8 | - | IMD |
| `jan.rain_days` | 2.3 | - | IMD |
| `jan.cloud_cover_pct` | 55.61 | % | *design choice* |
| `jan.diffuse_fraction_pct` | 45.90 | - | *switch* |
| `jan.wind10m_ms` | 2.96 | - | *design choice* |
| `jan.wind_direction_dominant` | 336 | - | *design choice* |
| `jan.pm25_ugm3` | 123.2 | - | *design choice* |
| `jan.dust_storm_days` | 0.01 | - | *design choice* |
| `jan.fog_days_observed_unused` | 1.2 | - | *design choice* |
| `feb.t_mean_c` | 16.5 | - | *design choice* |
| `feb.t_max_c` | 22.6 | - | *bound* |
| `feb.t_min_c` | 10.4 | - | *bound* |
| `feb.rh14_pct` | 42 | % | *design choice* |
| `feb.rainfall_mm` | 37.3 | - | *design choice* |
| `feb.rain_days` | 3.0 | - | *design choice* |
| `feb.cloud_cover_pct` | 43.47 | % | *design choice* |
| `feb.diffuse_fraction_pct` | 37.37 | - | *switch* |
| `feb.wind10m_ms` | 3.29 | - | *design choice* |
| `feb.wind_direction_dominant` | 335 | - | *design choice* |
| `feb.pm25_ugm3` | 70.9 | - | *design choice* |
| `feb.dust_storm_days` | 0.0 | - | *design choice* |
| `feb.fog_days_observed_unused` | 1.46 | - | *design choice* |
| `mar.t_mean_c` | 21.4 | - | *design choice* |
| `mar.t_max_c` | 28.0 | - | *bound* |
| `mar.t_min_c` | 14.7 | - | *bound* |
| `mar.rh14_pct` | 34 | % | *design choice* |
| `mar.rainfall_mm` | 27.4 | - | *design choice* |
| `mar.rain_days` | 2.2 | - | *design choice* |
| `mar.cloud_cover_pct` | 40.74 | % | *design choice* |
| `mar.diffuse_fraction_pct` | 34.40 | - | *switch* |
| `mar.wind10m_ms` | 3.49 | - | *design choice* |
| `mar.wind_direction_dominant` | 327 | - | *design choice* |
| `mar.pm25_ugm3` | 49.1 | - | *design choice* |
| `mar.dust_storm_days` | 0.063 | - | *design choice* |
| `mar.fog_days_observed_unused` | 0.5 | - | *design choice* |
| `apr.t_mean_c` | 27.5 | - | *design choice* |
| `apr.t_max_c` | 34.6 | - | *bound* |
| `apr.t_min_c` | 20.3 | - | *bound* |
| `apr.rh14_pct` | 23 | % | *design choice* |
| `apr.rainfall_mm` | 17.5 | - | *design choice* |
| `apr.rain_days` | 1.9 | - | *design choice* |
| `apr.cloud_cover_pct` | 43.47 | % | *design choice* |
| `apr.diffuse_fraction_pct` | 34.04 | - | *switch* |
| `apr.wind10m_ms` | 3.64 | - | *design choice* |
| `apr.wind_direction_dominant` | 321 | - | *design choice* |
| `apr.pm25_ugm3` | 40.5 | - | *design choice* |
| `apr.dust_storm_days` | 0.1 | - | *design choice* |
| `apr.fog_days_observed_unused` | 0.052 | - | *design choice* |
| `may.t_mean_c` | 31.7 | - | *design choice* |
| `may.t_max_c` | 38.6 | - | *bound* |
| `may.t_min_c` | 24.7 | - | *bound* |
| `may.rh14_pct` | 23 | % | *design choice* |
| `may.rainfall_mm` | 26.8 | - | *design choice* |
| `may.rain_days` | 2.2 | - | *design choice* |
| `may.cloud_cover_pct` | 46.19 | % | *design choice* |
| `may.diffuse_fraction_pct` | 36.68 | - | *switch* |
| `may.wind10m_ms` | 3.50 | - | *design choice* |
| `may.wind_direction_dominant` | 306 | - | *design choice* |
| `may.pm25_ugm3` | 48.7 | - | *design choice* |
| `may.dust_storm_days` | 0.1 | - | *design choice* |
| `may.fog_days_observed_unused` | 0.059 | - | *design choice* |
| `jun.t_mean_c` | 32.2 | - | *design choice* |
| `jun.t_max_c` | 37.7 | - | *bound* |
| `jun.t_min_c` | 26.7 | - | *bound* |
| `jun.rh14_pct` | 39 | % | *design choice* |
| `jun.rainfall_mm` | 146.7 | - | *design choice* |
| `jun.rain_days` | 6.5 | - | *design choice* |
| `jun.cloud_cover_pct` | 51.92 | % | *design choice* |
| `jun.diffuse_fraction_pct` | 40.08 | - | *switch* |
| `jun.wind10m_ms` | 3.27 | - | *design choice* |
| `jun.wind_direction_dominant` | 286 | - | *design choice* |
| `jun.pm25_ugm3` | 40.2 | - | *design choice* |
| `jun.dust_storm_days` | 0.1 | - | *design choice* |
| `jun.fog_days_observed_unused` | 0.8 | - | *design choice* |
| `jul.t_mean_c` | 30.5 | - | *design choice* |
| `jul.t_max_c` | 34.1 | - | *bound* |
| `jul.t_min_c` | 26.9 | - | *bound* |
| `jul.rh14_pct` | 62 | % | *design choice* |
| `jul.rainfall_mm` | 275.6 | - | *design choice* |
| `jul.rain_days` | 9.8 | - | *design choice* |
| `jul.cloud_cover_pct` | 68.47 | % | *design choice* |
| `jul.diffuse_fraction_pct` | 52.15 | - | *switch* |
| `jul.wind10m_ms` | 2.50 | - | *design choice* |
| `jul.wind_direction_dominant` | 202 | - | *design choice* |
| `jul.pm25_ugm3` | 24.4 | - | *design choice* |
| `jul.dust_storm_days` | 0.12 | - | *design choice* |
| `jul.fog_days_observed_unused` | 0.8 | - | *design choice* |
| `aug.t_mean_c` | 29.7 | - | *design choice* |
| `aug.t_max_c` | 33.2 | - | *bound* |
| `aug.t_min_c` | 26.2 | - | *bound* |
| `aug.rh14_pct` | 70 | % | *design choice* |
| `aug.rainfall_mm` | 273.0 | - | *design choice* |
| `aug.rain_days` | 11.1 | - | *design choice* |
| `aug.cloud_cover_pct` | 63.06 | % | *design choice* |
| `aug.diffuse_fraction_pct` | 47.23 | - | *switch* |
| `aug.wind10m_ms` | 2.37 | - | *design choice* |
| `aug.wind_direction_dominant` | 269 | - | *design choice* |
| `aug.pm25_ugm3` | 20.1 | - | *design choice* |
| `aug.dust_storm_days` | 0.02 | - | *design choice* |
| `aug.fog_days_observed_unused` | 1.062 | - | *design choice* |
| `sep.t_mean_c` | 28.7 | - | *design choice* |
| `sep.t_max_c` | 32.9 | - | *bound* |
| `sep.t_min_c` | 24.4 | - | *bound* |
| `sep.rh14_pct` | 59 | % | *design choice* |
| `sep.rainfall_mm` | 154.6 | - | *design choice* |
| `sep.rain_days` | 6.0 | - | *design choice* |
| `sep.cloud_cover_pct` | 37.65 | % | *design choice* |
| `sep.diffuse_fraction_pct` | 36.48 | - | *switch* |
| `sep.wind10m_ms` | 2.33 | - | *design choice* |
| `sep.wind_direction_dominant` | 319 | - | *design choice* |
| `sep.pm25_ugm3` | 27.9 | - | *design choice* |
| `sep.dust_storm_days` | 0.12 | - | *design choice* |
| `sep.fog_days_observed_unused` | 0.7 | - | *design choice* |
| `oct.t_mean_c` | 25.2 | - | *design choice* |
| `oct.t_max_c` | 32.0 | - | *bound* |
| `oct.t_min_c` | 18.4 | - | *bound* |
| `oct.rh14_pct` | 40 | % | *design choice* |
| `oct.rainfall_mm` | 14.2 | - | *design choice* |
| `oct.rain_days` | 0.8 | - | *design choice* |
| `oct.cloud_cover_pct` | 15.31 | % | *design choice* |
| `oct.diffuse_fraction_pct` | 26.02 | - | *switch* |
| `oct.wind10m_ms` | 2.59 | - | *design choice* |
| `oct.wind_direction_dominant` | 337 | - | *design choice* |
| `oct.pm25_ugm3` | 55.5 | - | *design choice* |
| `oct.dust_storm_days` | 0.1 | - | *design choice* |
| `oct.fog_days_observed_unused` | 1.2 | - | *design choice* |
| `nov.t_mean_c` | 19.7 | - | *design choice* |
| `nov.t_max_c` | 27.0 | - | *bound* |
| `nov.t_min_c` | 12.3 | - | *bound* |
| `nov.rh14_pct` | 40 | % | *design choice* |
| `nov.rainfall_mm` | 5.2 | - | *design choice* |
| `nov.rain_days` | 0.5 | - | *design choice* |
| `nov.cloud_cover_pct` | 27.60 | % | *design choice* |
| `nov.diffuse_fraction_pct` | 31.06 | - | *switch* |
| `nov.wind10m_ms` | 2.81 | - | *design choice* |
| `nov.wind_direction_dominant` | 337 | - | *design choice* |
| `nov.pm25_ugm3` | 91.6 | - | *design choice* |
| `nov.dust_storm_days` | 0.1 | - | *design choice* |
| `nov.fog_days_observed_unused` | 1.3 | - | *design choice* |
| `dec.t_mean_c` | 15.1 | - | *design choice* |
| `dec.t_max_c` | 22.1 | - | *bound* |
| `dec.t_min_c` | 8.0 | - | *bound* |
| `dec.rh14_pct` | 46 | % | *design choice* |
| `dec.rainfall_mm` | 22.3 | - | *design choice* |
| `dec.rain_days` | 1.3 | - | *design choice* |
| `dec.cloud_cover_pct` | 33.79 | % | *design choice* |
| `dec.diffuse_fraction_pct` | 32.94 | - | *switch* |
| `dec.wind10m_ms` | 2.88 | - | *design choice* |
| `dec.wind_direction_dominant` | 334 | - | *design choice* |
| `dec.pm25_ugm3` | 103.2 | - | *design choice* |
| `dec.dust_storm_days` | 0.1 | - | *design choice* |
| `dec.fog_days_observed_unused` | 1.4 | - | *design choice* |

### Annual

| parameter | value | units | source |
|:---|:---|:---|:---|
| `annual.dust_storm_days` | 0.2 | - | [imdpune.gov.in](https://imdpune.gov.in/hazardatlas/dustnew.html) |

### Pm25 ambient scale by period

| parameter | value | units | source |
|:---|:---|:---|:---|
| `pm25_ambient_scale_by_period` | 2030: 1.00; 2042: 0.88; 2055: 0.80 | - | [prana.cpcb.gov.in](https://prana.cpcb.gov.in/) |

---

## Costs, tariffs and technologies

`config/economics.yaml`


### (root)

| parameter | value | units | source |
|:---|:---|:---|:---|
| `currency` | INR | - | *design choice* |
| `base_year` | 2030 | year | *model structure* |
| `slices_per_year` | 864 | /yr | *model structure* |
| `inflation_assumption_annual` | 0.04 | - | *design choice* |
| `tariff_escalation_real_annual` | 0.0 | - | [pspcl.in](https://pspcl.in) |
| `end_of_life_cost_fraction` | 0.05 | - | *shares sum to 1* |
| `discount_rate` | 0.08 | - | *derived* |

### Multi period


All keys below sit under `multi_period`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `base_year` | 2030 | year | *model structure* |
| `discount_rate_real` | 0.0 | - | *model structure* |
| `farm_land_cells_by_period` | {"2030": 301, "2042": 301, "2055": 301} | - | *model structure* |
| `pv_density_ceiling_multiplier_by_period` | 2030: 1.00; 2042: 1.00; 2055: 1.00 | - | [qualenergia.it](https://www.qualenergia.it/wp-content/uploads/2024/06/ITRPV-15th-Edition-2024-2.pdf) |
| `pv_density_area_budget` | true | - | *model structure* |

### Scenario hooks


All keys below sit under `scenario_hooks`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `duck_curve_drift.import_multiplier_by_period_daypart` | 2042: {"10_12": 0.85, "12_14": 0.80, "14_16": 0.85, "18_20": 1.10, "20_22": 1.10}; 2055: {"10_12": 0.70, "12_14": 0.60, "14_16": 0.70, "18_20": 1.25, "20_22": 1.25} | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot%29) |
| `duck_curve_drift.export_multiplier_by_period` | 2030: 1.00; 2042: 0.70; 2055: 0.40 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot%29) |
| `carbon_price.price_inr_per_kgco2_by_period` | 2030: 0.0; 2042: 2.0; 2055: 4.0 | kgCO2 | [iea.org](https://www.iea.org/reports/world-energy-outlook-2024) |
| `reserve_margin.margin_fraction` | 0.15 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.grid_import` | 1.0 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.battery` | 1.0 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.v2g` | 0.5 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.biomass` | 0.9 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.wte` | 0.9 | - | [cea.nic.in](https://cea.nic.in/) |
| `reserve_margin.capacity_credit.biogas` | 0.9 | - | [cea.nic.in](https://cea.nic.in/) |
| `resilience_unserved.voll_inr_per_kwh` | 140 | ₹/kWh | [sciencedirect.com](https://www.sciencedirect.com/science/article/pii/S0928765524000010) |

### Stage d


All keys below sit under `stage_d`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `per_cell_buses` | false | - | *design choice* |
| `per_edge_cable_flow` | false | - | *design choice* |
| `dc_power_flow` | false | - | *design choice* |
| `p2p_trading` | false | - | *design choice* |
| `bundle_module_mix_lp_var` | false | - | *shares sum to 1* |
| `bundle_per_cell_tariff_split` | false | - | *shares sum to 1* |
| `bundle_industrial_cross_subsidy` | false | - | *design choice* |
| `bundle_pmsgy_tier_refinement` | false | - | *design choice* |
| `bundle_ev_placement` | false | - | *design choice* |
| `bundle_demand_diversity` | false | - | *design choice* |
| `reconciliation_tolerance_fraction` | 0.01 | - | *shares sum to 1* |
| `cell_aggregation_strategy` | none | - | *design choice* |
| `cable_thermal_kw_default` | 6000.0 | kW | *design choice* |
| `cable_resistance_ohm_per_km` | 0.275 | km | *design choice* |
| `cable_voltage_kv` | 11.0 | - | [pspcl.in](https://pspcl.in) |
| `dc_loss_piecewise_breakpoints` | [0.0, 0.5, 1.0] | - | *design choice* |
| `p2p_trading_tariff_inr_per_kwh` | 4.5 | ₹/kWh | *design choice* |

### Electrical network


All keys below sit under `electrical_network`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `enforce_thermal_caps` | true | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `cost_in_production` | true | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `cable_capex_inr_per_km.backbone_33kv_oh` | 885795.0 | ₹/km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `cable_capex_inr_per_km.backbone_33kv_ug` | 6141627.0 | ₹/km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `cable_capex_inr_per_km.dist_11kv_oh` | 544078.0 | ₹/km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `cable_capex_inr_per_km.dist_11kv_ug` | 4613879.0 | ₹/km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `underground_fraction.backbone_33kv` | 0.30 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `underground_fraction.dist_11kv` | 0.50 | - | [mohua.gov.in](https://www.mohua.gov.in/link/urdpfi-guidelines.php) |
| `cable_lifetime_years` | 40 | yr | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `substation.capex_inr_per_mva` | 1806000.0 | ₹/MVA | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `substation.mva_installed` | 300.0 | MVA | *design choice* |
| `substation.lifetime_years` | 35 | yr | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `substation.power_factor` | 0.95 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `voltage_tiers.backbone_33kv_thermal_kw` | 120000.0 | kW | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `voltage_tiers.dist_11kv_thermal_kw` | 30000.0 | kW | [cea.nic.in](https://cea.nic.in/wp-content/uploads/notification/2024/01/Final_Approved__Revised_Distribution_Planning_Criteria.pdf) |
| `backbone_assignment` | heuristic | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `backbone_n_feeders` | 4 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.capex_inr_per_kva` | 1500.0 | ₹ | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.no_load_loss_fraction` | 0.004 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.load_loss_fraction_at_rated` | 0.010 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.lifetime_years` | 25 | yr | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.sizing_headroom` | 1.25 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `transformer.share_of_ac_loss_fraction` | 0.5 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `conductor_resistance_ohm_per_km.dist_11kv` | 0.275 | km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `conductor_resistance_ohm_per_km.backbone_33kv` | 0.139 | km | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `loss_piecewise_segments` | 3 | - | [tgsouthernpower.org](https://tgsouthernpower.org/resources/PDF/Tarrif_Regulations/Cost-data%20FY23-24.pdf) |
| `reinforcement.base_dist_11kv_thermal_kw` | 45000 | kW | [cea.nic.in](https://cea.nic.in/wp-content/uploads/notification/2024/01/Final_Approved__Revised_Distribution_Planning_Criteria.pdf) |
| `reinforcement.base_backbone_33kv_thermal_kw` | 120000 | kW | [cea.nic.in](https://cea.nic.in/wp-content/uploads/notification/2024/01/Final_Approved__Revised_Distribution_Planning_Criteria.pdf) |
| `reinforcement.period_cap_multiplier` | 2030: 1.000; 2042: 1.317; 2055: 1.662 | - | [cea.nic.in](https://cea.nic.in/wp-content/uploads/notification/2024/01/Final_Approved__Revised_Distribution_Planning_Criteria.pdf) |

### Occupancy monthly modifier

| parameter | value | units | source |
|:---|:---|:---|:---|
| `occupancy_monthly_modifier.school.jun` | 0.25 | - | *design choice* |
| `occupancy_monthly_modifier.school.jul` | 0.60 | - | *design choice* |

### Behavioural 864


All keys below sit under `behavioural_864`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `lighting_evening_peak.hours` | [19, 20, 21, 22] | h | *design choice* |
| `lighting_evening_peak.multiplier` | 1.20 | - | *design choice* |
| `lighting_evening_peak.categories` | [low_income_residential, mid_income_residential, high_income_residential] | - | *label* |
| `wfh_day_of_week.office_reduction_fraction` | 0.06 | - | [nber.org](https://www.nber.org/digest/202012/working-homes-impact-electricity-use-pandemic) |
| `wfh_day_of_week.residential_daytime_uplift_fraction` | 0.06 | - | *shares sum to 1* |
| `wfh_day_of_week.residential_daytime_hours` | [10, 11, 12, 13, 14, 15] | h | *design choice* |
| `wfh_day_of_week.office_categories` | [office] | - | *label* |
| `wfh_day_of_week.residential_categories` | [low_income_residential, mid_income_residential, high_income_residential] | - | *label* |
| `wfh_day_of_week.day_types` | [weekday] | - | *design choice* |
| `festival_diwali_evening.months` | [oct, nov] | - | *design choice* |
| `festival_diwali_evening.hours` | [18, 19, 20, 21, 22] | h | *design choice* |
| `festival_diwali_evening.multiplier` | 1.15 | - | *design choice* |
| `festival_diwali_evening.categories` | [low_income_residential, mid_income_residential, high_income_residential] | - | *label* |
| `festival_diwali_evening.day_types` | [festival] | - | *design choice* |

### Lighting seasonal


All keys below sit under `lighting_seasonal`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `lighting_share_of_daypart` | 0.45 | - | BESCOM |
| `categories` | [low_income_residential, mid_income_residential, high_income_residential] | - | *label* |
| `dark_fraction_ratio_18_20.jan` | 1.1901 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.feb` | 1.1901 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.mar` | 1.1504 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.apr` | 0.9620 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.may` | 0.7736 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.jun` | 0.6050 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.jul` | 0.5950 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.aug` | 0.8033 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.sep` | 1.1603 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.oct` | 1.1901 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.nov` | 1.1901 | - | *shares sum to 1* |
| `dark_fraction_ratio_18_20.dec` | 1.1901 | - | *shares sum to 1* |

### Religious festival bumps


All keys below sit under `religious_festival_bumps`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `sikh.festival` | gurpurab | - | *design choice* |
| `sikh.months` | [nov] | - | *design choice* |
| `sikh.evening_hours` | [18, 19, 20, 21, 22] | h | *design choice* |
| `sikh.morning_hours` | [4, 5, 6, 7, 8] | h | *design choice* |
| `sikh.multiplier` | 1.40 | - | *design choice* |
| `hindu.festival` | diwali | - | *design choice* |
| `hindu.months` | [oct, nov] | - | *design choice* |
| `hindu.evening_hours` | [18, 19, 20, 21, 22, 23] | h | *design choice* |
| `hindu.multiplier` | 1.35 | - | *design choice* |
| `muslim.festival` | eid | - | *design choice* |
| `muslim.months` | [may] | - | *design choice* |
| `muslim.evening_hours` | [19, 20, 21, 22] | h | *design choice* |
| `muslim.morning_hours` | [6, 7, 8] | h | *design choice* |
| `muslim.multiplier` | 1.30 | - | *design choice* |
| `christian.festival` | christmas | - | *design choice* |
| `christian.months` | [dec] | - | *design choice* |
| `christian.evening_hours` | [18, 19, 20, 21, 22] | h | *design choice* |
| `christian.multiplier` | 1.25 | - | *design choice* |

### Electrical losses


All keys below sit under `electrical_losses`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `dc_loss_fraction` | 0.0 | - | [kb.solargis.com](https://kb.solargis.com/docs/pv-system-losses) |
| `ac_loss_fraction` | 0.020 | - | *shares sum to 1* |
| `pspcl_grid_loss_fraction` | 0.107 | - | [pspcl.in](https://pspcl.in) |
| `pspcl_grid_loss_by_period` | 2030: 0.107; 2042: 0.095; 2055: 0.085 | - | [pib.gov.in](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1897764) |

### Discount rates


All keys below sit under `discount_rates`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `social_planner` | 0.05 | - | *design choice* |
| `utility` | 0.065 | - | [cercind.gov.in](https://cercind.gov.in/2024/draft_reg/RE-Tariff-Regulations-EM.pdf) |
| `rwa_pooled` | 0.085 | - | *design choice* |
| `private_high_income` | 0.10 | - | *design choice* |
| `private_ews` | 0.125 | - | *design choice* |
| `social_ews` | 0.06 | - | [pmay-urban.gov.in](https://pmay-urban.gov.in/credit-linked-subsidy-scheme%29) |

### Rooftop owner weights


All keys below sit under `rooftop_owner_weights`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `gov_ews` | 0.0741 | - | *shares sum to 1* |
| `gov_public` | 0.1335 | - | *shares sum to 1* |
| `rwa` | 0.1463 | - | *shares sum to 1* |
| `private` | 0.6461 | - | *shares sum to 1* |

### Rooftop owner actors


All keys below sit under `rooftop_owner_actors`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `gov_ews` | social_ews | - | *design choice* |
| `gov_public` | social_planner | - | *design choice* |
| `rwa` | rwa_pooled | - | *design choice* |
| `private` | private_high_income | - | *design choice* |

### Technologies


All keys below sit under `technologies`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `rooftop_pv.capex_inr_per_kwp` | 35500 | ₹/kWp | [mnre.gov.in](https://mnre.gov.in) |
| `rooftop_pv.opex_fraction_of_capex_per_year` | 0.012 | - | *shares sum to 1* |
| `rooftop_pv.lifetime_years` | 25 | yr | *design choice* |
| `rooftop_pv.operational_emission_kgco2_per_kwh` | 0.0 | kgCO2/kWh | *design choice* |
| `rooftop_pv.degradation_per_year` | 0.012 | /yr | *model structure* |
| `rooftop_pv.capex_real_decline_per_year` | 0.012 | /yr | *model structure* |
| `rooftop_pv.base_annual_capacity_factor` | 0.1731 | - | *derived* |
| `rooftop_pv.module_types.mono_perc.share` | 0.65 | - | *design choice* |
| `rooftop_pv.module_types.mono_perc.efficiency` | 0.21 | - | *design choice* |
| `rooftop_pv.module_types.mono_perc.capex_inr_per_kwp` | 38000 | ₹/kWp | *design choice* |
| `rooftop_pv.module_types.mono_perc.temp_coefficient_per_c` | 0.0035 | - | *design choice* |
| `rooftop_pv.module_types.poly_si.share` | 0.25 | - | *design choice* |
| `rooftop_pv.module_types.poly_si.efficiency` | 0.17 | - | *design choice* |
| `rooftop_pv.module_types.poly_si.capex_inr_per_kwp` | 32000 | ₹/kWp | *design choice* |
| `rooftop_pv.module_types.poly_si.temp_coefficient_per_c` | 0.0040 | - | *design choice* |
| `rooftop_pv.module_types.thin_film_cdte.share` | 0.10 | - | *design choice* |
| `rooftop_pv.module_types.thin_film_cdte.efficiency` | 0.14 | - | *design choice* |
| `rooftop_pv.module_types.thin_film_cdte.capex_inr_per_kwp` | 28000 | ₹/kWp | *design choice* |
| `rooftop_pv.module_types.thin_film_cdte.temp_coefficient_per_c` | 0.0025 | - | *design choice* |
| `solar_farm.capex_inr_per_kwp` | 27000 | ₹/kWp | *design choice* |
| `solar_farm.opex_fraction_of_capex_per_year` | 0.01 | - | *shares sum to 1* |
| `solar_farm.lifetime_years` | 25 | yr | *design choice* |
| `solar_farm.operational_emission_kgco2_per_kwh` | 0.0 | kgCO2/kWh | *design choice* |
| `solar_farm.inter_row_shading_derate` | 0.00021 | - | *design choice* |
| `solar_farm.degradation_per_year` | 0.010 | /yr | *model structure* |
| `solar_farm.capex_real_decline_per_year` | 0.015 | /yr | BNEF; NREL |
| `solar_farm.base_annual_capacity_factor` | 0.1731 | - | *derived* |
| `li_ion_battery.capex_inr_per_kwh` | 9000 | ₹/kWh | [nrel.gov](https://www.nrel.gov/docs/fy23osti/85332.pdf%29) |
| `li_ion_battery.max_capacity_hours_of_peak` | 8.0 | h | *bound* |
| `li_ion_battery.opex_fraction_of_capex_per_year` | 0.02 | - | *shares sum to 1* |
| `li_ion_battery.lifetime_years` | 10 | yr | *design choice* |
| `li_ion_battery.round_trip_efficiency` | 0.90 | - | *derived* |
| `li_ion_battery.max_depth_of_discharge` | 0.90 | - | *design choice* |
| `li_ion_battery.c_rate_per_hour` | 0.5 | - | SECI |
| `li_ion_battery.capex_real_decline_per_year` | 0.030 | /yr | *model structure* |
| `li_ion_battery.calendar_fade_per_year` | 0.02 | /yr | *model structure* |
| `li_ion_battery.operational_emission_kgco2_per_kwh` | 0.0 | kgCO2/kWh | *design choice* |
| `v2g_charger.capex_inr_per_unit` | 42000 | ₹/unit | *design choice* |
| `v2g_charger.opex_inr_per_unit_per_year` | 1500 | ₹/unit | *model structure* |
| `v2g_charger.lifetime_years` | 15 | yr | *design choice* |
| `v2g_charger.nominal_power_kw_per_unit` | 7.0 | kW | *design choice* |
| `v2g_charger.available_kwh_per_unit_per_day` | 6.0 | kWh | *design choice* |
| `v2g_charger.available_kwh_per_unit_per_day_by_period` | 2030: 6.0; 2042: 8.0; 2055: 9.5 | kWh | [iea.org](https://www.iea.org/reports/global-ev-outlook-2024%29) |
| `v2g_charger.cycle_degradation_inr_per_kwh` | 2.0 | ₹/kWh | *design choice* |
| `biomass_chp.capex_inr_per_kw_e` | 100000 | ₹/kW | [cercind.gov.in](https://www.cercind.gov.in/2020/regulation/159_reg.pdf) |
| `biomass_chp.opex_fraction_of_capex_per_year` | 0.04 | - | *shares sum to 1* |
| `biomass_chp.lifetime_years` | 25 | yr | *design choice* |
| `biomass_chp.electrical_efficiency` | 0.243 | - | [cercind.gov.in](https://cercind.gov.in) |
| `biomass_chp.operating_hours_per_year` | 7000 | /yr | *model structure* |
| `biomass_chp.fuel_cost_inr_per_tonne` | 2000 | ₹/t | *design choice* |
| `biomass_chp.fuel_calorific_value_mj_per_kg` | 12.97 | - | [cercind.gov.in](https://cercind.gov.in) |
| `biomass_chp.operational_emission_kgco2_per_kwh` | 0.0556 | kgCO2/kWh | *design choice* |
| `biomass_chp.capacity_cap_kw_e` | 13500 | kW | [peda.gov.in](https://www.peda.gov.in/biomass-power-projects) |
| `biomass_chp.annual_straw_available_tonnes` | 130000 | t | TERI |
| `biomass_chp.fuel_monthly_availability_fraction.jan` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.feb` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.mar` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.apr` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.may` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.jun` | 0.95 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.jul` | 0.85 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.aug` | 0.80 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.sep` | 0.80 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.oct` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.nov` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_availability_fraction.dec` | 1.00 | - | *shares sum to 1* |
| `biomass_chp.fuel_monthly_cost_multiplier.jan` | 1.05 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.feb` | 1.07 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.mar` | 1.10 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.apr` | 1.12 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.may` | 1.15 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.jun` | 1.17 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.jul` | 1.20 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.aug` | 1.22 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.sep` | 1.25 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.oct` | 1.00 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.nov` | 1.00 | - | *derived* |
| `biomass_chp.fuel_monthly_cost_multiplier.dec` | 1.02 | - | *derived* |
| `biomass_chp.fuel_price_multiplier_by_period` | 2030: 1.00; 2042: 1.25; 2055: 1.50 | - | [caqm.nic.in](https://caqm.nic.in/WriteReadData/LINKS/Punjab%20State%20action%20plan%20%281%29e4a64b10-7638-490f-9ae8-8c09ce27082f.pdf) |
| `tracked_pv.capex_multiplier_vs_fixed` | 1.12 | - | [taypro.in](https://taypro.in/blog/solar-panel-installation-cost-for-utility-scale-in-india%29) |
| `tracked_pv.yield_multiplier_vs_fixed` | 1.18 | - | *derived* |
| `tracked_pv.land_ratio_vs_fixed` | 1.33 | - | [nrel.gov](https://www.nrel.gov/docs/fy13osti/56290.pdf) |
| `tracked_pv.opex_fraction_of_capex_per_year` | 0.012 | - | *shares sum to 1* |
| `tracked_pv.lifetime_years` | 25 | yr | *design choice* |
| `tracked_pv.operational_emission_kgco2_per_kwh` | 0.0 | kgCO2/kWh | *design choice* |
| `wte_plant.design_population` | 250000 | persons | *design choice* |
| `wte_plant.capex_inr_per_kw_e` | 180000 | ₹/kW | *design choice* |
| `wte_plant.opex_fraction_of_capex_per_year` | 0.06 | - | *shares sum to 1* |
| `wte_plant.lifetime_years` | 20 | yr | *design choice* |
| `wte_plant.electrical_efficiency` | 0.20 | - | *derived* |
| `wte_plant.operating_hours_per_year` | 7500 | /yr | *model structure* |
| `wte_plant.fuel_cost_inr_per_tonne` | 0 | ₹/t | *design choice* |
| `wte_plant.fuel_calorific_value_mj_per_kg` | 6.0 | - | *design choice* |
| `wte_plant.msw_kg_per_cap_per_day` | 0.5 | - | *bound* |
| `wte_plant.operational_emission_kgco2_per_kwh` | 0.20 | kgCO2/kWh | *design choice* |
| `wte_plant.landfill_diversion_credit_inr_per_kwh` | 3.0 | ₹/kWh | *design choice* |
| `biogas_plant.capacity_cap_kw_e` | 1125 | kW | *bound* |
| `biogas_plant.capex_inr_per_kw_e` | 122222 | ₹/kW | *design choice* |
| `biogas_plant.opex_fraction_of_capex_per_year` | 0.045 | - | *shares sum to 1* |
| `biogas_plant.lifetime_years` | 20 | yr | *design choice* |
| `biogas_plant.electrical_efficiency` | 0.288 | - | *derived* |
| `biogas_plant.operating_hours_per_year` | 7800 | /yr | *model structure* |
| `biogas_plant.fuel_cost_inr_per_kwh` | 0.5556 | ₹/kWh | *design choice* |
| `biogas_plant.operational_emission_kgco2_per_kwh` | 0.0222 | kgCO2/kWh | *design choice* |
| `thermal_cold_storage.capex_inr_per_kwh_thermal` | 4000 | ₹/kWh | *design choice* |
| `thermal_cold_storage.opex_fraction_of_capex_per_year` | 0.015 | - | *shares sum to 1* |
| `thermal_cold_storage.lifetime_years` | 25 | yr | *design choice* |
| `thermal_cold_storage.round_trip_efficiency` | 0.80 | - | *derived* |
| `thermal_cold_storage.operational_emission_kgco2_per_kwh` | 0.0 | kgCO2/kWh | *design choice* |
| `thermal_cold_storage.c_rate_per_hour` | 0.2 | - | *design choice* |
| `thermal_cold_storage.kwh_per_m2_floor_area` | 0.05 | kWh | *design choice* |
| `solar_thermal.collector_type` | flat_plate | - | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.lifetime_years` | 15 | yr | *design choice* |
| `solar_thermal.lifetime_years_etc_sensitivity` | 5 | yr | *design choice* |
| `solar_thermal.collector_tilt_deg` | 46 | deg | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.pv_reference_tilt_deg` | 29 | deg | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.jan` | 1.054 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.feb` | 2.055 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.mar` | 2.584 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.apr` | 2.724 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.may` | 2.421 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.jun` | 2.014 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.jul` | 1.591 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.aug` | 1.870 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.sep` | 2.330 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.oct` | 2.490 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.nov` | 1.834 | kWh | *design choice* |
| `solar_thermal.monthly_kwh_per_m2_per_day.dec` | 1.427 | kWh | *design choice* |
| `solar_thermal.annual_kwh_per_m2` | 742 | kWh | *design choice* |
| `solar_thermal.bucket_average_hold_hours` | 12.5 | h | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.jan` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.2196) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.feb` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3733) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.mar` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.4385) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.apr` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.4415) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.may` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3848) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.jun` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3181) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.jul` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.2571) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.aug` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3063) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.sep` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3821) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.oct` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.4188) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.nov` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.3263) | kW | *model structure* |
| `solar_thermal.kw_per_m2_by_month_daypart.dec` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.277) | kW | *model structure* |
| `solar_thermal.reference_inlet_c` | 12.0 | - | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.m2_per_100_lpd` | 2.0 | m² | *design choice* |
| `solar_thermal.tank_litres_per_m2_collector` | 50 | m² | *design choice* |
| `solar_thermal.eta0` | 0.67 | - | IS 12933 |
| `solar_thermal.a1_w_per_m2_k` | 5.5 | W/m² | *design choice* |
| `solar_thermal.eta0_keymark_sensitivity` | 0.73 | - | *design choice* |
| `solar_thermal.a1_keymark_sensitivity` | 4.5 | - | *design choice* |
| `solar_thermal.iam_b0` | 0.10 | - | *design choice* |
| `solar_thermal.iam_diffuse_effective_angle_deg` | 58 | deg | *switch* |
| `solar_thermal.collector_inlet_rule` | mean_of_inlet_and_setpoint | - | *design choice* |
| `solar_thermal.apply_soiling` | true | - | *design choice* |
| `solar_thermal.row_spacing_gcr_at_collector_tilt` | 0.486 | - | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.row_spacing_gcr_at_pv_tilt` | 0.558 | - | *design choice* |
| `solar_thermal.apply_row_spacing_penalty` | false | - | *design choice* |
| `solar_thermal.capex_inr_per_m2` | 14000 | ₹/m² | *design choice* |
| `solar_thermal.capex_inr_per_m2_low` | 12000 | ₹/m² | *design choice* |
| `solar_thermal.capex_inr_per_m2_high` | 17500 | ₹/m² | *design choice* |
| `solar_thermal.tank_share_of_system_capex` | 0.35 | - | *shares sum to 1* |
| `solar_thermal.mnre_benchmark_inr_per_m2_fpc_historic` | 3300 | ₹/m² | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.avoided_geyser_capex_inr_per_system` | 11000 | ₹ | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.backup_element_kw` | 2.0 | kW | *design choice* |
| `solar_thermal.opex_fraction_of_capex_per_year` | 0.02 | - | *shares sum to 1* |
| `solar_thermal.pump_parasitic_kwh_per_m2_per_year` | 0.0 | /yr | *model structure* |
| `solar_thermal.tank_standing_loss_frac_per_hour` | 0.02 | - | [mnre.gov.in](https://mnre.gov.in) |
| `solar_thermal.embodied_kgco2_per_m2` | 338.5 | kgCO2 | *design choice* |
| `solar_thermal.mandate_plot_threshold_sq_yd` | 500 | - | *design choice* |
| `solar_thermal.apply_subsidy_asymmetry` | false | - | *design choice* |
| `solar_thermal.pv_pm_surya_ghar_cap_inr` | 78000 | ₹ | *bound* |
| `solar_thermal.owner_weights.rwa_pooled` | 0.4983 | - | *shares sum to 1* |
| `solar_thermal.owner_weights.private_high_income` | 0.4205 | - | *shares sum to 1* |
| `solar_thermal.owner_weights.social_ews` | 0.0756 | - | *shares sum to 1* |
| `solar_thermal.owner_weights.social_planner` | 0.0056 | - | *shares sum to 1* |
| `solar_thermal.owner_actors.low_income_residential` | social_ews | - | *design choice* |
| `solar_thermal.owner_actors.mid_income_residential` | rwa_pooled | - | *design choice* |
| `solar_thermal.owner_actors.high_income_residential` | private_high_income | - | *design choice* |
| `solar_thermal.owner_actors.school` | social_planner | - | *design choice* |
| `solar_thermal.owner_actors.healthcare` | social_planner | - | *design choice* |
| `solar_thermal.owner_actors.public_services` | social_planner | - | *design choice* |
| `solar_thermal.owner_actors.hotel_guesthouse` | private_high_income | - | *design choice* |
| `solar_thermal.owner_actors.restaurant_food_service` | private_high_income | - | *design choice* |
| `solar_thermal.roof_pair_constraint` | true | - | *design choice* |

### Carbon objective


All keys below sit under `carbon_objective`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `alphas` | [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0] | - | *design choice* |
| `carbon_price_inr_per_kgco2` | 2.5 | kgCO2 | [cercind.gov.in](https://cercind.gov.in/regulations/205-Noti.pdf) |
| `include_embodied_carbon` | true | - | *switch* |

### Embodied carbon


All keys below sit under `embodied_carbon`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `end_of_life_carbon_fraction` | 0.10 | - | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `rooftop_pv_kgco2_per_kwp` | 810 | kgCO2/kWp | [ise.fraunhofer.de](https://www.ise.fraunhofer.de/content/dam/ise/de/documents/publications/conference-paper/wcpec-8/Reichel_5DV234.pdf) |
| `solar_farm_kgco2_per_kwp` | 810 | kgCO2/kWp | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `tracked_pv_extra_kgco2_per_kwp` | 10 | kgCO2/kWp | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `by_build_year.rooftop_pv_kgco2_per_kwp` | {2030: 810, 2042: 550, 2055: 450} | kgCO2/kWp | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `by_build_year.solar_farm_kgco2_per_kwp` | {2030: 810, 2042: 550, 2055: 450} | kgCO2/kWp | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `li_ion_battery_kgco2_per_kwh` | 100 | kgCO2/kWh | [theicct.org](https://theicct.org/wp-content/uploads/2021/06/EV-life-cycle-GHG_ICCT-Briefing_09022018_vF.pdf) |
| `v2g_charger_kgco2_per_unit` | 250 | kgCO2 | *design choice* |
| `biomass_chp_kgco2_per_kw_e` | 1666.67 | kgCO2 | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `wte_plant_kgco2_per_kw_e` | 2200 | kgCO2 | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `biogas_plant_kgco2_per_kw_e` | 1333.33 | kgCO2 | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `thermal_storage_kgco2_per_kwh` | 15 | kgCO2/kWh | [iea-pvps.org](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_Task12_LCA_Guidelines.pdf) |
| `internal_network.cable_11kv_kgco2_per_km` | 52000.0 | kgCO2 | [enwl.co.uk](https://www.enwl.co.uk/globalassets/about-us/regulatory-information/documents/environment-report/embodied-carbon-calculations-for-substation-projects/ec---designer-calculation---hutton-end.pdf) |
| `internal_network.cable_33kv_kgco2_per_km` | 41800.0 | kgCO2 | [enwl.co.uk](https://www.enwl.co.uk/globalassets/about-us/regulatory-information/documents/environment-report/embodied-carbon-calculations-for-substation-projects/ec---designer-calculation---hutton-end.pdf) |
| `internal_network.transformer_kgco2_per_mva` | 6955.4 | kgCO2 | [enwl.co.uk](https://www.enwl.co.uk/globalassets/about-us/regulatory-information/documents/environment-report/embodied-carbon-calculations-for-substation-projects/ec---designer-calculation---hutton-end.pdf) |
| `internal_network.substation_kgco2_per_mva` | 6955.4 | kgCO2 | [enwl.co.uk](https://www.enwl.co.uk/globalassets/about-us/regulatory-information/documents/environment-report/embodied-carbon-calculations-for-substation-projects/ec---designer-calculation---hutton-end.pdf) |

### Reliability


All keys below sit under `reliability`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `outage_hours_per_year` | 120 | /yr | [seforall.org](https://www.seforall.org/system/files/2021-08/SEforALL_Carbon-emissions-methodology-note.pdf) |
| `diesel_genset_cost_inr_per_kwh` | 25.0 | ₹/kWh | *design choice* |
| `diesel_genset_emission_kgco2_per_kwh` | 0.75 | kgCO2/kWh | *design choice* |
| `reliability_coverage_fraction` | 0.20 | - | *shares sum to 1* |
| `symmetric_diesel_backup.chp_outage_availability` | 1.0 | - | *design choice* |

### Dynamic tariff


All keys below sit under `dynamic_tariff`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `enabled_default` | false | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.00_02` | 1.05 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.02_04` | 1.00 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.04_06` | 1.05 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.06_08` | 0.92 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.08_10` | 0.82 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.10_12` | 0.55 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.12_14` | 0.48 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.14_16` | 0.55 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.16_18` | 0.95 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.18_20` | 1.70 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.20_22` | 1.92 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `intraday_band_multiplier.22_24` | 1.18 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `tnd_loss_fraction` | 0.07 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `network_charge_inr_per_kwh` | 0.70 | ₹/kWh | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `cross_subsidy_inr_per_kwh` | 0.0 | ₹/kWh | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `duty_fraction` | 0.05 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `retail_cap_inr_per_kwh` | 11.0 | ₹/kWh | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `retail_floor_inr_per_kwh` | 1.5 | ₹/kWh | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `export_pegged_to_wholesale` | true | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `level_calibration_multiplier` | 0.95 | - | [iexindia.com](https://www.iexindia.com/market-data/day-ahead-market/market-snapshot) |
| `monthly_rtc_inr_per_kwh` | 4.4, 4.4, ... (12 values, 4.4 to 5.8) | ₹/kWh | [cercind.gov.in](https://cercind.gov.in) |

### Grid


All keys below sit under `grid`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `import_tariff_inr_per_kwh.solar` | 4.80 | ₹/kWh | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/01/20260102144277158.pdf) |
| `import_tariff_inr_per_kwh.off_peak` | 5.40 | ₹/kWh | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/01/20260102144277158.pdf) |
| `import_tariff_inr_per_kwh.shoulder` | 6.00 | ₹/kWh | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/01/20260102144277158.pdf) |
| `import_tariff_inr_per_kwh.peak` | 8.00 | ₹/kWh | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/01/20260102144277158.pdf) |
| `import_tariff_inr_per_kwh.super_peak` | 9.50 | ₹/kWh | [cdnbbsr.s3waas.gov.in](https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/01/20260102144277158.pdf) |
| `export_tariff_inr_per_kwh` | 3.0 | ₹/kWh | SECI |
| `industrial_cross_subsidy_inr_per_kwh` | 1.05 | ₹/kWh | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329184924412.pdf) |
| `pspcl_premium_factor` | 1.07 | - | [cea.nic.in](https://cea.nic.in/cdm-co2-baseline-database/) |
| `emission_factor_kgco2_per_kwh` | 0.55 | kgCO2/kWh | *derived* |
| `emission_factor_trajectory_kgco2_per_kwh` | 2025: 0.70; 2030: 0.55; 2035: 0.45; 2040: 0.35; 2050: 0.20 | kgCO2/kWh | *derived* |
| `use_grid_decarb_trajectory` | true | - | *switch* |
| `project_lifetime_years` | 25 | yr | *design choice* |
| `import_capacity_limit_kw` | 600000 | kW | [cea.nic.in](https://cea.nic.in) |
| `export_capacity_limit_kw` | 180000 | kW | [cea.nic.in](https://cea.nic.in/wp-content/uploads/notification/2024/01/Final_Approved__Revised_Distribution_Planning_Criteria.pdf) |
| `net_metering_cap_kwp_per_consumer` | 1000 | kWp | *bound* |
| `net_metering_cap_binding` | false | - | *bound* |
| `import_tariff_subsidy_fraction` | 0.0 | - | *shares sum to 1* |
| `rooftop_pv_capex_subsidy_fraction` | 0.30 | - | *shares sum to 1* |
| `pmsgy_continuation_scenario.scenario` | decay_linear_to_2040 | - | *label* |
| `pmsgy_continuation_scenario.hold_years` | 3 | yr | *label* |
| `pmsgy_continuation_scenario.fade_start_year` | 3 | year | *model structure* |
| `pmsgy_continuation_scenario.fade_end_year` | 10 | year | *model structure* |
| `pmsgy_continuation_scenario.fraction_2030_2032` | 0.30 | - | *label* |
| `pmsgy_continuation_scenario.fraction_2040_onwards` | 0.0 | - | *label* |

### Equity report


All keys below sit under `equity_report`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ews_social_tariff_inr_per_kwh` | 3.0 | ₹/kWh | *design choice* |
| `pspcl_domestic_first_slab_inr_per_kwh` | 5.40 | ₹/kWh | [seci.co.in](https://www.seci.co.in) |
| `use_tou_bands_for_non_ews` | true | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `commercial_tariff_premium_inr_per_kwh` | 0.0 | ₹/kWh | [pspcl.in](https://pspcl.in) |
| `bau_residential_tariff_basis` | per_slice_tou | - | *design choice* |
| `p2p_exclude_ews` | true | - | *design choice* |
| `pmsgy_effective_subsidy_by_tier.low` | 0.60 | - | [pmsuryaghar.gov.in](https://pmsuryaghar.gov.in) |
| `pmsgy_effective_subsidy_by_tier.mid` | 0.55 | - | [pmsuryaghar.gov.in](https://pmsuryaghar.gov.in) |
| `pmsgy_effective_subsidy_by_tier.high` | 0.35 | - | [pmsuryaghar.gov.in](https://pmsuryaghar.gov.in) |
| `pmsgy_rwa_common_area_inr_per_kw` | 18000 | ₹/kW | [mnre.gov.in](https://mnre.gov.in) |
| `pmsgy_free_kwh_per_month` | 300 | kWh | [mnre.gov.in](https://mnre.gov.in) |

### Calendar


All keys below sit under `calendar.months`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `jan` | {days: 31, weekday: 21, weekend: 8, festival: 2} | - | [pspcl.in](https://pspcl.in) |
| `feb` | {days: 28, weekday: 20, weekend: 8, festival: 0} | - | [pspcl.in](https://pspcl.in) |
| `mar` | {days: 31, weekday: 21, weekend: 8, festival: 2} | - | [pspcl.in](https://pspcl.in) |
| `apr` | {days: 30, weekday: 19, weekend: 8, festival: 3} | - | [pspcl.in](https://pspcl.in) |
| `may` | {days: 31, weekday: 22, weekend: 8, festival: 1} | - | [pspcl.in](https://pspcl.in) |
| `jun` | {days: 30, weekday: 22, weekend: 8, festival: 0} | - | [pspcl.in](https://pspcl.in) |
| `jul` | {days: 31, weekday: 22, weekend: 8, festival: 1} | - | [pspcl.in](https://pspcl.in) |
| `aug` | {days: 31, weekday: 21, weekend: 8, festival: 2} | - | [pspcl.in](https://pspcl.in) |
| `sep` | {days: 30, weekday: 21, weekend: 8, festival: 1} | - | [pspcl.in](https://pspcl.in) |
| `oct` | {days: 31, weekday: 19, weekend: 8, festival: 4} | - | [pspcl.in](https://pspcl.in) |
| `nov` | {days: 30, weekday: 17, weekend: 8, festival: 5} | - | [pspcl.in](https://pspcl.in) |
| `dec` | {days: 31, weekday: 22, weekend: 8, festival: 1} | - | [pspcl.in](https://pspcl.in) |

### Seasonal tod


All keys below sit under `seasonal_tod.overrides_by_month`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `jan` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `feb` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `mar` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `apr` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `may` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `oct` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `nov` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |
| `dec` | {"18_20": shoulder, "20_22": shoulder} | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329183246514.pdf) |

### Pv capacity factor


All keys below sit under `pv_capacity_factor`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `soiling_renormalise_to_gsa_anchor` | true | - | [re.jrc.ec.europa.eu](https://re.jrc.ec.europa.eu/pvg_tools/en/) |
| `monthly_modifier.jan` | 0.5417 | - | *derived* |
| `monthly_modifier.feb` | 0.7845 | - | *derived* |
| `monthly_modifier.mar` | 0.9491 | - | *derived* |
| `monthly_modifier.apr` | 1.0214 | - | *derived* |
| `monthly_modifier.may` | 0.9727 | - | *derived* |
| `monthly_modifier.jun` | 0.8522 | - | *derived* |
| `monthly_modifier.jul` | 0.7241 | - | *derived* |
| `monthly_modifier.aug` | 0.7723 | - | *derived* |
| `monthly_modifier.sep` | 0.8477 | - | *derived* |
| `monthly_modifier.oct` | 0.8652 | - | *derived* |
| `monthly_modifier.nov` | 0.6945 | - | *derived* |
| `monthly_modifier.dec` | 0.6037 | - | *derived* |
| `daypart_shape_by_month.jan` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.8276) | - | *model structure* |
| `daypart_shape_by_month.feb` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7914) | - | *model structure* |
| `daypart_shape_by_month.mar` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7483) | - | *model structure* |
| `daypart_shape_by_month.apr` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7146) | - | *model structure* |
| `daypart_shape_by_month.may` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.6875) | - | *model structure* |
| `daypart_shape_by_month.jun` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.6668) | - | *model structure* |
| `daypart_shape_by_month.jul` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.6673) | - | *model structure* |
| `daypart_shape_by_month.aug` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.6983) | - | *model structure* |
| `daypart_shape_by_month.sep` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7251) | - | *model structure* |
| `daypart_shape_by_month.oct` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7614) | - | *model structure* |
| `daypart_shape_by_month.nov` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.7954) | - | *model structure* |
| `daypart_shape_by_month.dec` | 00_02: 0.0000, 02_04: 0.0000, ... (12 entries, 0 to 0.8266) | - | *model structure* |
| `daypart_shape.00_02` | 0.00 | - | *model structure* |
| `daypart_shape.02_04` | 0.00 | - | *model structure* |
| `daypart_shape.04_06` | 0.00 | - | *model structure* |
| `daypart_shape.06_08` | 0.08 | - | *model structure* |
| `daypart_shape.08_10` | 0.35 | - | *model structure* |
| `daypart_shape.10_12` | 0.55 | - | *model structure* |
| `daypart_shape.12_14` | 0.65 | - | *model structure* |
| `daypart_shape.14_16` | 0.60 | - | *model structure* |
| `daypart_shape.16_18` | 0.30 | - | *model structure* |
| `daypart_shape.18_20` | 0.06 | - | *model structure* |
| `daypart_shape.20_22` | 0.00 | - | *model structure* |
| `daypart_shape.22_24` | 0.00 | - | *model structure* |

### Pv orientations


All keys below sit under `pv_orientations`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `south_fixed.yield_multiplier_vs_south` | 1.00 | - | *derived* |
| `south_fixed.daypart_shape.00_02` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.02_04` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.04_06` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.06_08` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.08_10` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.10_12` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.12_14` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.14_16` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.16_18` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.18_20` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.20_22` | 1.00 | - | *model structure* |
| `south_fixed.daypart_shape.22_24` | 1.00 | - | *model structure* |
| `east_west_split.yield_multiplier_vs_south` | 0.86 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.00_02` | 1.1072 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.02_04` | 1.1072 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.04_06` | 1.1072 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.06_08` | 1.4948 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.08_10` | 1.3287 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.10_12` | 0.9412 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.12_14` | 0.7751 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.14_16` | 0.9412 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.16_18` | 1.3287 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.18_20` | 1.4948 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.20_22` | 1.1072 | - | *shares sum to 1* |
| `east_west_split.daypart_shape.22_24` | 1.1072 | - | *shares sum to 1* |
| `vertical_facade.yield_multiplier_vs_south` | 1.00 | - | *derived* |
| `vertical_facade.daypart_shape.00_02` | 1.00 | - | *model structure* |
| `vertical_facade.daypart_shape.02_04` | 1.00 | - | *model structure* |
| `vertical_facade.daypart_shape.04_06` | 1.00 | - | *model structure* |
| `vertical_facade.daypart_shape.06_08` | 1.40 | - | *model structure* |
| `vertical_facade.daypart_shape.08_10` | 1.05 | - | *model structure* |
| `vertical_facade.daypart_shape.10_12` | 0.45 | - | *model structure* |
| `vertical_facade.daypart_shape.12_14` | 0.25 | - | *model structure* |
| `vertical_facade.daypart_shape.14_16` | 0.45 | - | *model structure* |
| `vertical_facade.daypart_shape.16_18` | 1.05 | - | *model structure* |
| `vertical_facade.daypart_shape.18_20` | 1.40 | - | *model structure* |
| `vertical_facade.daypart_shape.20_22` | 1.00 | - | *model structure* |
| `vertical_facade.daypart_shape.22_24` | 1.00 | - | *model structure* |
| `single_axis_tracked.yield_multiplier_vs_south` | 1.18 | - | *derived* |
| `single_axis_tracked.daypart_shape.00_02` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.02_04` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.04_06` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.06_08` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.08_10` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.10_12` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.12_14` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.14_16` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.16_18` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.18_20` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.20_22` | 1.00 | - | *model structure* |
| `single_axis_tracked.daypart_shape.22_24` | 1.00 | - | *model structure* |

### Demand side response


All keys below sit under `demand_side_response`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `comfort_cost_inr_per_kwh` | 1.5 | ₹/kWh | *design choice* |
| `comfort_cost_by_category_inr_per_kwh.ac_precool` | 0.5 | ₹/kWh | *design choice* |
| `comfort_cost_by_category_inr_per_kwh.geyser_thermal` | 2.0 | ₹/kWh | *design choice* |
| `comfort_cost_by_category_inr_per_kwh.ev_charging_window` | 1.5 | ₹/kWh | *design choice* |
| `aggregate_shiftable_fraction_in_peak` | 0.10 | - | [eta-publications.lbl.gov](https://eta-publications.lbl.gov/publications/findings-advanced-demand-response) |
| `shift_window_hours` | 4 | h | *design choice* |
| `categories.ac_precool.shiftable_fraction_of_cooling` | 0.30 | - | *shares sum to 1* |
| `categories.ac_precool.shift_window_hours` | 3 | h | *label* |
| `categories.geyser_thermal.shiftable_fraction_of_dhw` | 0.50 | - | *shares sum to 1* |
| `categories.geyser_thermal.shift_window_hours` | 12 | h | *label* |
| `categories.ev_charging_window.shiftable_fraction_of_load` | 1.00 | - | *shares sum to 1* |
| `categories.ev_charging_window.shift_window_hours` | 12 | h | *label* |

### Allume solshare


All keys below sit under `allume_solshare`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `capex_premium_fraction` | 0.10 | - | *shares sum to 1* |
| `default_apartment_uptake_fraction` | 0.60 | - | *shares sum to 1* |
| `apartment_roof_share_of_total` | 0.50 | - | *shares sum to 1* |

### Biosolar roof


All keys below sit under `biosolar_roof`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `pv_yield_multiplier` | 1.06 | - | *derived* |
| `cooling_demand_multiplier` | 0.93 | - | *derived* |
| `roof_capex_multiplier` | 1.35 | - | *derived* |
| `default_built_uptake_fraction` | 0.30 | - | *shares sum to 1* |
| `cooling_share_of_total_demand` | 0.30 | - | *shares sum to 1* |

### Bipv facade


All keys below sit under `bipv_facade`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `applies_above_height_m` | 18.0 | m | *design choice* |
| `yield_multiplier_vs_rooftop` | 0.60 | - | *derived* |
| `capex_multiplier_vs_rooftop` | 2.00 | - | *derived* |
| `kwp_per_meter_of_height` | 10.0 | kWp | *design choice* |
| `default_uptake_fraction` | 0.50 | - | *shares sum to 1* |

### Solar carport


All keys below sit under `solar_carport`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `kwp_per_cell_default` | 800 | kWp | *design choice* |
| `kwp_per_cell_min` | 500 | kWp | *bound* |
| `kwp_per_cell_max` | 1500 | kWp | *bound* |
| `capex_multiplier_vs_ground_mount` | 1.20 | - | *derived* |
| `default_uptake_fraction` | 0.40 | - | *shares sum to 1* |

### Floating pv


All keys below sit under `floating_pv`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `eligible_land_uses` | [blue_space] | - | [peda.gov.in](https://www.peda.gov.in/solar-canals-built-in-sidhwan-and-ghaggar) |
| `kwp_per_cell_default` | 1500 | kWp | [peda.gov.in](https://www.peda.gov.in/solar-canals-built-in-sidhwan-and-ghaggar) |
| `capex_multiplier_vs_ground_mount` | 1.10 | - | *derived* |
| `yield_multiplier_vs_ground_mount` | 1.04 | - | [peda.gov.in](https://www.peda.gov.in/solar-canals-built-in-sidhwan-and-ghaggar) |
| `default_uptake_fraction` | 0.30 | - | [peda.gov.in](https://www.peda.gov.in/solar-canals-built-in-sidhwan-and-ghaggar) |
| `canal.kwp_per_cell` | 210 | kWp | [peda.gov.in](https://www.peda.gov.in/solar-canals-built-in-sidhwan-and-ghaggar) |
| `site_selection.min_cluster_size` | 2 | - | [nrel.gov](https://www.nrel.gov/docs/fy22osti/80695.pdf) |

### Ppa


All keys below sit under `ppa`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `counterparties.data_centre_offsite.offtake_kw_constant` | 25000 | kW | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.tariff_inr_per_kwh` | 5.99 | ₹/kWh | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.wheeling_charge_inr_per_kwh` | 0.657 | ₹/kWh | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.cross_subsidy_surcharge_inr_per_kwh` | 1.11 | ₹/kWh | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.interconnection_capex_inr` | 10,000,000 | ₹ | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.legal_filing_capex_inr` | 1,500,000 | ₹ | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.annual_admin_inr` | 150,000 | ₹ | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.ppa_capex_lifetime_yrs` | 25 | - | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite.bound_by_surplus_not_baseload` | true | - | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `counterparties.data_centre_offsite_re_concession.offtake_kw_constant` | 25000 | kW | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.tariff_inr_per_kwh` | 5.99 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.wheeling_charge_inr_per_kwh` | 0.12 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.cross_subsidy_surcharge_inr_per_kwh` | 0.0 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.wheeling_loss_fraction` | 0.022 | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.interconnection_capex_inr` | 10,000,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.legal_filing_capex_inr` | 1,500,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.annual_admin_inr` | 150,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.ppa_capex_lifetime_yrs` | 25 | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.data_centre_offsite_re_concession.bound_by_surplus_not_baseload` | true | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.offtake_kw_constant` | 8000 | kW | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.tariff_inr_per_kwh` | 5.5 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.wheeling_charge_inr_per_kwh` | 1.27 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.cross_subsidy_surcharge_inr_per_kwh` | 1.20 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.interconnection_capex_inr` | 7,000,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.legal_filing_capex_inr` | 1,500,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.annual_admin_inr` | 150,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.ppa_capex_lifetime_yrs` | 25 | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.corporate_industrial.bound_by_surplus_not_baseload` | true | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.offtake_kw_constant` | 12000 | kW | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.tariff_inr_per_kwh` | 4.5 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.wheeling_charge_inr_per_kwh` | 0.50 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.cross_subsidy_surcharge_inr_per_kwh` | 0.0 | ₹/kWh | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.interconnection_capex_inr` | 8,000,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.legal_filing_capex_inr` | 2,000,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.annual_admin_inr` | 150,000 | ₹ | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.ppa_capex_lifetime_yrs` | 25 | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `counterparties.group_captive.bound_by_surplus_not_baseload` | true | - | [cbre.co.in](https://www.cbre.co.in/insights) |
| `max_ppa_share_of_district_demand` | 0.60 | - | [cbre.co.in](https://www.cbre.co.in/insights) |

### Green purchase


All keys below sit under `green_purchase`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `gen_price_inr_per_kwh` | 2.97 | ₹/kWh | [mercomindia.com](https://www.mercomindia.com/punjab-regulator-approves-tariff-400-mw-solar-procurement) |
| `inkind_tw_charge_fraction` | 0.02 | - | [docs.pspcl.in](https://docs.pspcl.in/docs/cecommercial2520250329184924412.pdf) |
| `oa_loss_fraction` | 0.0400 | - | *shares sum to 1* |
| `css_inr_per_kwh` | 0.85 | ₹/kWh | [pspcl.in](https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf) |
| `additional_surcharge_inr_per_kwh` | 0.0 | ₹/kWh | [ksandk.com](https://ksandk.com/newsletter/pserc-adds-surcharges-for-stranded-capacity/) |
| `annual_admin_inr` | 300000 | ₹ | *design choice* |
| `contracted_mw_max` | 200.0 | MW | *bound* |
| `banking` | none | - | [pspcl.in](https://www.pspcl.in/LatestNewsDoc/Banking_Procedure_for_Green_Energy_Open_Access_Consumers_04_09_2025_04_49_11.pdf) |
| `emission_factor_kgco2_per_kwh` | 0.0 | kgCO2/kWh | [pib.gov.in](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1842737) |

### Boundary opex


All keys below sit under `boundary_opex`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `waste_gate_fee_inr_per_tonne` | 600 | ₹/t | [cdn.cseindia.org](https://cdn.cseindia.org/userfiles/Swati.pdf) |
| `waste_residues_tonnes_by_period` | {"2030": 2995, "2042": 8470, "2055": 14401} | t | *model structure* |
| `canal_water_charge_inr_per_kl` | 5.0 | ₹ | *design choice* |
| `canal_water_kl_per_year` | 4312969 | /yr | [cpheeo.gov.in](http://cpheeo.gov.in) |

### Interconnection


All keys below sit under `interconnection`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `capex_inr` | 1200000000 | ₹ | *design choice* |
| `lifetime_years` | 35 | yr | *design choice* |
| `actor` | utility | - | *design choice* |
| `sizing.design_basis_mw` | 600.0 | MW | *design choice* |

### Farm land rent


All keys below sit under `farm_land_rent`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `mode` | agricultural | - | *switch* |
| `agricultural_inr_per_ha_yr` | 250000 | ₹ | [ras.org.in](https://ras.org.in/articles/214/pdf/Tenancy_in_Punjab.pdf) |
| `market_value_inr_per_ha` | 30000000 | ₹ | *design choice* |
| `market_opportunity_rate_real` | 0.05 | - | *design choice* |

### Battery coupling


All keys below sit under `battery_coupling`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `ac_traditional_round_trip_efficiency` | 0.90 | - | *derived* |
| `dc_native_round_trip_efficiency` | 0.94 | - | *derived* |
| `default_mode` | ac_traditional | - | *design choice* |
| `auxiliary_energy_consumption_fraction` | 0.05 | - | [cercind.gov.in](https://cercind.gov.in/2025/draft_reg/DN_TC-2nd.pdf) |

### Pv orientation defaults by category


All keys below sit under `pv_orientation_defaults_by_category`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential` | east_west_split | - | *design choice* |
| `mid_income_residential` | east_west_split | - | *design choice* |
| `high_income_residential` | south_fixed | - | *design choice* |
| `school` | south_fixed | - | *design choice* |
| `office` | south_fixed | - | *design choice* |
| `shopping_centre` | south_fixed | - | *design choice* |
| `retail_highstreet` | east_west_split | - | *design choice* |
| `restaurant_food_service` | south_fixed | - | *design choice* |
| `hotel_guesthouse` | south_fixed | - | *design choice* |
| `healthcare` | south_fixed | - | *design choice* |
| `light_industry` | south_fixed | - | *design choice* |
| `warehouse_cold_storage` | south_fixed | - | *switch* |
| `public_services` | south_fixed | - | *design choice* |
| `religious` | south_fixed | - | *design choice* |

### Cooling intensity dwelling correction

| parameter | value | units | source |
|:---|:---|:---|:---|
| `cooling_intensity_dwelling_correction.high_income_residential` | 0.8333 | - | *design choice* |

### Cooling technologies


All keys below sit under `cooling_technologies`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `fan_only.w_per_m2_peak` | 1.0 | W/m² | [pib.gov.in](https://www.pib.gov.in/pressreleasepage.aspx?prid=1598508&reg=48&lang=2) |
| `fan_only.monsoon_effectiveness` | 1.0 | - | [pib.gov.in](https://www.pib.gov.in/pressreleasepage.aspx?prid=1598508&reg=48&lang=2) |
| `fan_only.cop` | 0.0 | - | [pib.gov.in](https://www.pib.gov.in/pressreleasepage.aspx?prid=1598508&reg=48&lang=2) |
| `desert_cooler.w_per_m2_peak` | 8.0 | W/m² | *design choice* |
| `desert_cooler.monsoon_effectiveness` | 0.60 | - | *design choice* |
| `desert_cooler.cop` | 8.0 | - | *design choice* |
| `window_ac_3star.w_per_m2_peak` | 18.0 | W/m² | [beeindia.gov.in](https://beeindia.gov.in) |
| `window_ac_3star.monsoon_effectiveness` | 1.0 | - | *design choice* |
| `window_ac_3star.cop` | 2.8 | - | *design choice* |
| `inverter_ac_5star.w_per_m2_peak` | 17.5 | W/m² | [consumer.bluestarindia.com](https://consumer.bluestarindia.com/products/inverter-split-ac-p-series-1-5-ton-5-star) |
| `inverter_ac_5star.monsoon_effectiveness` | 1.0 | - | *design choice* |
| `inverter_ac_5star.cop` | 4.5 | - | *design choice* |

### Cooling tech mix by category


All keys below sit under `cooling_tech_mix_by_category`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential` | {fan_only: 0.20, desert_cooler: 0.70, window_ac_3star: 0.10, inverter_ac_5star: 0.0} | - | [nature.com](https://www.nature.com/articles/s41467-024-52028-8) |
| `mid_income_residential` | {fan_only: 0.0,  desert_cooler: 0.20, window_ac_3star: 0.32, inverter_ac_5star: 0.48} | - | *shares sum to 1* |
| `high_income_residential` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.0,  inverter_ac_5star: 1.0} | - | *shares sum to 1* |
| `school` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.50, inverter_ac_5star: 0.50} | - | *shares sum to 1* |
| `office` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.30, inverter_ac_5star: 0.70} | - | *shares sum to 1* |
| `shopping_centre` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.20, inverter_ac_5star: 0.80} | - | *shares sum to 1* |
| `retail_highstreet` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.50, inverter_ac_5star: 0.50} | - | *shares sum to 1* |
| `restaurant_food_service` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.40, inverter_ac_5star: 0.60} | - | *shares sum to 1* |
| `hotel_guesthouse` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.30, inverter_ac_5star: 0.70} | - | *shares sum to 1* |
| `healthcare` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.20, inverter_ac_5star: 0.80} | - | *shares sum to 1* |
| `light_industry` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.50, inverter_ac_5star: 0.50} | - | *shares sum to 1* |
| `warehouse_cold_storage` | {fan_only: 0.0,  desert_cooler: 0.0,  window_ac_3star: 0.0,  inverter_ac_5star: 1.0} | - | *switch* |
| `public_services` | {fan_only: 1.0,  desert_cooler: 0.0,  window_ac_3star: 0.0,  inverter_ac_5star: 0.0} | - | *shares sum to 1* |
| `religious` | {fan_only: 1.0,  desert_cooler: 0.0,  window_ac_3star: 0.0,  inverter_ac_5star: 0.0} | - | *shares sum to 1* |

### Heating loads


All keys below sit under `heating_loads`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `per_category_peak_w_per_m2.low_income_residential` | 5.08 | W/m² | [ceew.in](https://www.ceew.in) |
| `per_category_peak_w_per_m2.mid_income_residential` | 20.4 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.high_income_residential` | 8.4 | W/m² | [beeindia.gov.in](https://beeindia.gov.in) |
| `per_category_peak_w_per_m2.school` | 4.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.office` | 5.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.shopping_centre` | 2.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.retail_highstreet` | 2.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.restaurant_food_service` | 5.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.hotel_guesthouse` | 8.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.healthcare` | 7.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.light_industry` | 0.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.warehouse_cold_storage` | 0.0 | W/m² | *switch* |
| `per_category_peak_w_per_m2.public_services` | 2.0 | W/m² | *design choice* |
| `per_category_peak_w_per_m2.religious` | 1.0 | W/m² | *design choice* |
| `heating_baseline_c` | 18.0 | - | *design choice* |
| `heating_factor_by_month.jan` | 1.00 | - | *derived* |
| `heating_factor_by_month.feb` | 0.85 | - | *derived* |
| `heating_factor_by_month.mar` | 0.40 | - | *derived* |
| `heating_factor_by_month.apr` | 0.10 | - | *derived* |
| `heating_factor_by_month.may` | 0.00 | - | *derived* |
| `heating_factor_by_month.jun` | 0.00 | - | *derived* |
| `heating_factor_by_month.jul` | 0.00 | - | *derived* |
| `heating_factor_by_month.aug` | 0.00 | - | *derived* |
| `heating_factor_by_month.sep` | 0.00 | - | *derived* |
| `heating_factor_by_month.oct` | 0.10 | - | *derived* |
| `heating_factor_by_month.nov` | 0.50 | - | *derived* |
| `heating_factor_by_month.dec` | 0.95 | - | *derived* |
| `heating_daypart_shape.00_02` | 0.40 | - | *model structure* |
| `heating_daypart_shape.02_04` | 0.50 | - | *model structure* |
| `heating_daypart_shape.04_06` | 0.80 | - | *model structure* |
| `heating_daypart_shape.06_08` | 1.00 | - | *model structure* |
| `heating_daypart_shape.08_10` | 0.60 | - | *model structure* |
| `heating_daypart_shape.10_12` | 0.20 | - | *model structure* |
| `heating_daypart_shape.12_14` | 0.10 | - | *model structure* |
| `heating_daypart_shape.14_16` | 0.10 | - | *model structure* |
| `heating_daypart_shape.16_18` | 0.30 | - | *model structure* |
| `heating_daypart_shape.18_20` | 0.70 | - | *model structure* |
| `heating_daypart_shape.20_22` | 0.80 | - | *model structure* |
| `heating_daypart_shape.22_24` | 0.60 | - | *model structure* |
| `dhw_share_of_peak_by_category.low_income_residential` | 0.9213 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.mid_income_residential` | 0.9020 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.high_income_residential` | 0.857 | - | [beeindia.gov.in](https://beeindia.gov.in) |
| `dhw_share_of_peak_by_category.school` | 0.20 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.office` | 0.25 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.shopping_centre` | 0.20 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.retail_highstreet` | 0.20 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.restaurant_food_service` | 0.80 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.hotel_guesthouse` | 0.75 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.healthcare` | 0.70 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.public_services` | 0.25 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.religious` | 0.30 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.light_industry` | 0.00 | - | *shares sum to 1* |
| `dhw_share_of_peak_by_category.warehouse_cold_storage` | 0.00 | - | *switch* |
| `dhw.setpoint_c` | 60.0 | - | [law.resource.org](https://law.resource.org/pub/in/bis/S05/is.2082.1993.pdf%29) |
| `dhw.bath_temperature_c` | 40.0 | - | *design choice* |
| `dhw.inlet_temperature_field` | t_mean_c | - | [beeindia.gov.in](https://beeindia.gov.in/en/programmesbuildings/ecbc) |
| `dhw.hot_water_lpcd_by_category.low_income_residential` | 15.0 | - | [prod-qt-images.s3.amazonaws.com](https://prod-qt-images.s3.amazonaws.com/indiawaterportal/import/sites/default/files/iwp2/Users_Handbook_Solar_Water_Heater_MNRE_2010.pdf) |
| `dhw.hot_water_lpcd_by_category.mid_income_residential` | 20.0 | - | [prod-qt-images.s3.amazonaws.com](https://prod-qt-images.s3.amazonaws.com/indiawaterportal/import/sites/default/files/iwp2/Users_Handbook_Solar_Water_Heater_MNRE_2010.pdf) |
| `dhw.hot_water_lpcd_by_category.high_income_residential` | 40.0 | - | [prod-qt-images.s3.amazonaws.com](https://prod-qt-images.s3.amazonaws.com/indiawaterportal/import/sites/default/files/iwp2/Users_Handbook_Solar_Water_Heater_MNRE_2010.pdf) |
| `dhw.people_per_household_by_category.low_income_residential` | 4.91 | - | *design choice* |
| `dhw.people_per_household_by_category.mid_income_residential` | 4.50 | - | *design choice* |
| `dhw.people_per_household_by_category.high_income_residential` | 4.25 | - | *design choice* |
| `dhw.appliance_kw_by_category.low_income_residential` | 1.0 | kW | *design choice* |
| `dhw.appliance_kw_by_category.mid_income_residential` | 2.0 | kW | IS 2082 |
| `dhw.appliance_kw_by_category.high_income_residential` | 2.0 | kW | *design choice* |
| `dhw.running_hours_by_category.school` | 1.0 | h | *design choice* |
| `dhw.running_hours_by_category.office` | 1.0 | h | *design choice* |
| `dhw.running_hours_by_category.shopping_centre` | 1.0 | h | *design choice* |
| `dhw.running_hours_by_category.retail_highstreet` | 1.0 | h | *design choice* |
| `dhw.running_hours_by_category.restaurant_food_service` | 3.0 | h | *design choice* |
| `dhw.running_hours_by_category.hotel_guesthouse` | 3.0 | h | *design choice* |
| `dhw.running_hours_by_category.healthcare` | 3.0 | h | *design choice* |
| `dhw.running_hours_by_category.public_services` | 1.0 | h | *design choice* |
| `dhw.running_hours_by_category.religious` | 1.0 | h | *design choice* |
| `dhw.daypart_profile_by_class.low.06_08` | 0.70 | - | *model structure* |
| `dhw.daypart_profile_by_class.low.08_10` | 0.15 | - | *model structure* |
| `dhw.daypart_profile_by_class.low.18_20` | 0.10 | - | *model structure* |
| `dhw.daypart_profile_by_class.low.20_22` | 0.05 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.04_06` | 0.05 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.06_08` | 0.45 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.08_10` | 0.15 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.16_18` | 0.05 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.18_20` | 0.15 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.20_22` | 0.12 | - | *model structure* |
| `dhw.daypart_profile_by_class.mid.22_24` | 0.03 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.04_06` | 0.06 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.06_08` | 0.34 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.08_10` | 0.16 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.10_12` | 0.05 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.12_14` | 0.03 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.14_16` | 0.03 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.16_18` | 0.06 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.18_20` | 0.13 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.20_22` | 0.11 | - | *model structure* |
| `dhw.daypart_profile_by_class.high.22_24` | 0.03 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.06_08` | 0.15 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.08_10` | 0.15 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.10_12` | 0.12 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.12_14` | 0.14 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.14_16` | 0.12 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.16_18` | 0.10 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.18_20` | 0.12 | - | *model structure* |
| `dhw.daypart_profile_by_class.commercial.20_22` | 0.10 | - | *model structure* |
| `space_heating.hdd_baseline_c` | 18.0 | - | IMD |
| `space_heating.hdd_temperature_field` | t_mean_c | - | *design choice* |
| `space_heating.appliance_kw` | 2.0 | kW | [beeindia.gov.in](https://beeindia.gov.in) |
| `space_heating.running_hours_by_category.low_income_residential` | 2.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.mid_income_residential` | 3.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.high_income_residential` | 4.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.school` | 4.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.office` | 5.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.shopping_centre` | 5.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.retail_highstreet` | 5.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.restaurant_food_service` | 4.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.hotel_guesthouse` | 6.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.healthcare` | 8.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.public_services` | 4.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.running_hours_by_category.religious` | 2.0 | h | [ceew.in](https://www.ceew.in/sites/default/files/CEEW-IRES-Awareness-and-adoption-of-EE-in-Indian-homes-07Oct20.pdf) |
| `space_heating.daypart_profile_by_class.low.18_20` | 0.45 | - | *model structure* |
| `space_heating.daypart_profile_by_class.low.20_22` | 0.45 | - | *model structure* |
| `space_heating.daypart_profile_by_class.low.22_24` | 0.10 | - | *model structure* |
| `space_heating.daypart_profile_by_class.mid.06_08` | 0.15 | - | *model structure* |
| `space_heating.daypart_profile_by_class.mid.16_18` | 0.10 | - | *model structure* |
| `space_heating.daypart_profile_by_class.mid.18_20` | 0.28 | - | *model structure* |
| `space_heating.daypart_profile_by_class.mid.20_22` | 0.30 | - | *model structure* |
| `space_heating.daypart_profile_by_class.mid.22_24` | 0.17 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.00_02` | 0.10 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.02_04` | 0.09 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.04_06` | 0.10 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.06_08` | 0.13 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.08_10` | 0.05 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.16_18` | 0.07 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.18_20` | 0.14 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.20_22` | 0.16 | - | *model structure* |
| `space_heating.daypart_profile_by_class.high.22_24` | 0.16 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.06_08` | 0.15 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.08_10` | 0.20 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.10_12` | 0.15 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.12_14` | 0.12 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.14_16` | 0.12 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.16_18` | 0.15 | - | *model structure* |
| `space_heating.daypart_profile_by_class.commercial.18_20` | 0.11 | - | *model structure* |

### Cooling factors


All keys below sit under `cooling_factors`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `cooling_base_c` | 24.0 | - | [pib.gov.in](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1598508) |
| `cooling_factor_by_month.jan` | 0.00 | - | *derived* |
| `cooling_factor_by_month.feb` | 0.05 | - | *derived* |
| `cooling_factor_by_month.mar` | 0.25 | - | *derived* |
| `cooling_factor_by_month.apr` | 0.55 | - | *derived* |
| `cooling_factor_by_month.may` | 0.90 | - | *derived* |
| `cooling_factor_by_month.jun` | 1.00 | - | *derived* |
| `cooling_factor_by_month.jul` | 0.80 | - | *derived* |
| `cooling_factor_by_month.aug` | 0.75 | - | *derived* |
| `cooling_factor_by_month.sep` | 0.65 | - | *derived* |
| `cooling_factor_by_month.oct` | 0.40 | - | *derived* |
| `cooling_factor_by_month.nov` | 0.15 | - | *derived* |
| `cooling_factor_by_month.dec` | 0.00 | - | *derived* |
| `residential_cooling.daypart_profile.00_02` | 0.21 | - | *model structure* |
| `residential_cooling.daypart_profile.02_04` | 0.18 | - | *model structure* |
| `residential_cooling.daypart_profile.04_06` | 0.12 | - | *model structure* |
| `residential_cooling.daypart_profile.06_08` | 0.03 | - | *model structure* |
| `residential_cooling.daypart_profile.08_10` | 0.02 | - | *model structure* |
| `residential_cooling.daypart_profile.10_12` | 0.02 | - | *model structure* |
| `residential_cooling.daypart_profile.12_14` | 0.02 | - | *model structure* |
| `residential_cooling.daypart_profile.14_16` | 0.03 | - | *model structure* |
| `residential_cooling.daypart_profile.16_18` | 0.04 | - | *model structure* |
| `residential_cooling.daypart_profile.18_20` | 0.07 | - | *model structure* |
| `residential_cooling.daypart_profile.20_22` | 0.10 | - | *model structure* |
| `residential_cooling.daypart_profile.22_24` | 0.16 | - | *model structure* |
| `residential_cooling.equivalent_full_load_hours.low_income_residential` | 9.24 | h | *derived* |
| `residential_cooling.equivalent_full_load_hours.mid_income_residential` | 8.95 | h | *derived* |
| `residential_cooling.equivalent_full_load_hours.high_income_residential` | 8.16 | h | *derived* |
| `cooling_daypart_shape.00_02` | 0.40 | - | *model structure* |
| `cooling_daypart_shape.02_04` | 0.30 | - | *model structure* |
| `cooling_daypart_shape.04_06` | 0.20 | - | *model structure* |
| `cooling_daypart_shape.06_08` | 0.20 | - | *model structure* |
| `cooling_daypart_shape.08_10` | 0.40 | - | *model structure* |
| `cooling_daypart_shape.10_12` | 0.70 | - | *model structure* |
| `cooling_daypart_shape.12_14` | 0.90 | - | *model structure* |
| `cooling_daypart_shape.14_16` | 1.00 | - | *model structure* |
| `cooling_daypart_shape.16_18` | 0.95 | - | *model structure* |
| `cooling_daypart_shape.18_20` | 0.85 | - | *model structure* |
| `cooling_daypart_shape.20_22` | 0.75 | - | *model structure* |
| `cooling_daypart_shape.22_24` | 0.55 | - | *model structure* |
| `monsoon_months` | ["jun", "jul", "aug", "sep"] | - | *derived* |
| `cooling_daypart_shape_monsoon.00_02` | 0.55 | - | *model structure* |
| `cooling_daypart_shape_monsoon.02_04` | 0.50 | - | *model structure* |
| `cooling_daypart_shape_monsoon.04_06` | 0.40 | - | *model structure* |
| `cooling_daypart_shape_monsoon.06_08` | 0.30 | - | *model structure* |
| `cooling_daypart_shape_monsoon.08_10` | 0.45 | - | *model structure* |
| `cooling_daypart_shape_monsoon.10_12` | 0.60 | - | *model structure* |
| `cooling_daypart_shape_monsoon.12_14` | 0.70 | - | *model structure* |
| `cooling_daypart_shape_monsoon.14_16` | 0.80 | - | *model structure* |
| `cooling_daypart_shape_monsoon.16_18` | 0.85 | - | *model structure* |
| `cooling_daypart_shape_monsoon.18_20` | 1.00 | - | *model structure* |
| `cooling_daypart_shape_monsoon.20_22` | 0.95 | - | *model structure* |
| `cooling_daypart_shape_monsoon.22_24` | 0.75 | - | *model structure* |

### Base demand profile


All keys below sit under `base_demand_profile`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `low_income_residential.weekday` | 00_02: 0.50, 02_04: 0.45, ... (12 entries, 0.4 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `low_income_residential.weekend` | 00_02: 0.55, 02_04: 0.50, ... (12 entries, 0.5 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `low_income_residential.festival` | 00_02: 0.65, 02_04: 0.55, ... (12 entries, 0.55 to 1.05) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `mid_income_residential.weekday` | 00_02: 0.45, 02_04: 0.40, ... (12 entries, 0.3 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `mid_income_residential.weekend` | 00_02: 0.50, 02_04: 0.45, ... (12 entries, 0.45 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `mid_income_residential.festival` | 00_02: 0.60, 02_04: 0.50, ... (12 entries, 0.5 to 1.05) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `high_income_residential.weekday` | 00_02: 0.55, 02_04: 0.50, ... (12 entries, 0.4 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `high_income_residential.weekend` | 00_02: 0.60, 02_04: 0.55, ... (12 entries, 0.55 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `high_income_residential.festival` | 00_02: 0.70, 02_04: 0.60, ... (12 entries, 0.55 to 1.05) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `school.weekday` | 00_02: 0.05, 02_04: 0.05, ... (12 entries, 0.05 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `school.weekend` | 00_02: 0.05, 02_04: 0.05, ... (12 entries, 0.05 to 0.2) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `school.festival` | 00_02: 0.05, 02_04: 0.05, ... (12 entries, 0.05 to 0.15) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `office.weekday` | 00_02: 0.10, 02_04: 0.10, ... (12 entries, 0.1 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `office.weekend` | 00_02: 0.10, 02_04: 0.10, ... (12 entries, 0.1 to 0.25) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `office.festival` | 00_02: 0.10, 02_04: 0.10, ... (12 entries, 0.1 to 0.25) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `shopping_centre.weekday` | 00_02: 0.20, 02_04: 0.15, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `shopping_centre.weekend` | 00_02: 0.20, 02_04: 0.15, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `shopping_centre.festival` | 00_02: 0.30, 02_04: 0.20, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `retail_highstreet.weekday` | 00_02: 0.20, 02_04: 0.15, ... (12 entries, 0.15 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `retail_highstreet.weekend` | 00_02: 0.20, 02_04: 0.15, ... (12 entries, 0.15 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `retail_highstreet.festival` | 00_02: 0.30, 02_04: 0.20, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `restaurant_food_service.weekday` | 00_02: 0.25, 02_04: 0.15, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `restaurant_food_service.weekend` | 00_02: 0.30, 02_04: 0.20, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `restaurant_food_service.festival` | 00_02: 0.40, 02_04: 0.25, ... (12 entries, 0.15 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `hotel_guesthouse.weekday` | 00_02: 0.65, 02_04: 0.60, ... (12 entries, 0.5 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `hotel_guesthouse.weekend` | 00_02: 0.75, 02_04: 0.70, ... (12 entries, 0.55 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `hotel_guesthouse.festival` | 00_02: 0.85, 02_04: 0.75, ... (12 entries, 0.65 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `healthcare.weekday` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.65 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `healthcare.weekend` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.65 to 0.8) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `healthcare.festival` | 00_02: 0.70, 02_04: 0.65, ... (12 entries, 0.65 to 0.8) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `light_industry.weekday` | 00_02: 0.20, 02_04: 0.20, ... (12 entries, 0.2 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `light_industry.weekend` | 00_02: 0.20, 02_04: 0.20, ... (12 entries, 0.2 to 0.4) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `light_industry.festival` | 00_02: 0.20, 02_04: 0.20, ... (12 entries, 0.2 to 0.35) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `warehouse_cold_storage.weekday` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.65 to 0.9) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `warehouse_cold_storage.weekend` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.65 to 0.75) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `warehouse_cold_storage.festival` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.65 to 0.75) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `public_services.weekday` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.3 to 0.85) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `public_services.weekend` | 00_02: 0.65, 02_04: 0.65, ... (12 entries, 0.25 to 0.85) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `public_services.festival` | 00_02: 0.75, 02_04: 0.70, ... (12 entries, 0.3 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `religious.weekday` | 00_02: 0.15, 02_04: 0.10, ... (12 entries, 0.1 to 0.8) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `religious.weekend` | 00_02: 0.20, 02_04: 0.10, ... (12 entries, 0.1 to 0.95) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |
| `religious.festival` | 00_02: 0.45, 02_04: 0.25, ... (12 entries, 0.25 to 1) | - | [energy.prayaspune.org](https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns) |

### Ev adoption


All keys below sit under `ev_adoption`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `default_scenario` | 2030_default | - | *label* |
| `scenarios.2030_slow` | {fleet_share: 0.08, household_adoption: 0.07, v2g_capable_fraction: 0.20} | - | *label* |
| `scenarios.2030_default` | {fleet_share: 0.20, household_adoption: 0.18, v2g_capable_fraction: 0.35} | - | *label* |
| `scenarios.2030_fast` | {fleet_share: 0.35, household_adoption: 0.30, v2g_capable_fraction: 0.55} | - | *label* |
| `ev_kwh_per_office_employee_per_day` | 2.5 | kWh | *design choice* |
| `ev_charger_type_mix_office.fast` | {share: 0.20, kwh_per_session: 5.0,  duty_cycle: 0.50} | - | *shares sum to 1* |
| `ev_charger_type_mix_office.slow` | {share: 0.65, kwh_per_session: 12.0, duty_cycle: 0.25} | - | *shares sum to 1* |
| `ev_charger_type_mix_office.phev` | {share: 0.15, kwh_per_session: 2.5,  duty_cycle: 0.20} | - | *shares sum to 1* |
| `ev_charging_daypart_shape_residential.00_02` | 0.03 | - | *model structure* |
| `ev_charging_daypart_shape_residential.02_04` | 0.02 | - | *model structure* |
| `ev_charging_daypart_shape_residential.04_06` | 0.02 | - | *model structure* |
| `ev_charging_daypart_shape_residential.06_08` | 0.03 | - | *model structure* |
| `ev_charging_daypart_shape_residential.08_10` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_residential.10_12` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_residential.12_14` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_residential.14_16` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_residential.16_18` | 0.13 | - | *model structure* |
| `ev_charging_daypart_shape_residential.18_20` | 0.37 | - | *model structure* |
| `ev_charging_daypart_shape_residential.20_22` | 0.28 | - | *model structure* |
| `ev_charging_daypart_shape_residential.22_24` | 0.12 | - | *model structure* |
| `ev_charging_daypart_shape_office.00_02` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_office.02_04` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_office.04_06` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_office.06_08` | 0.05 | - | *model structure* |
| `ev_charging_daypart_shape_office.08_10` | 0.20 | - | *model structure* |
| `ev_charging_daypart_shape_office.10_12` | 0.25 | - | *model structure* |
| `ev_charging_daypart_shape_office.12_14` | 0.20 | - | *model structure* |
| `ev_charging_daypart_shape_office.14_16` | 0.15 | - | *model structure* |
| `ev_charging_daypart_shape_office.16_18` | 0.10 | - | *model structure* |
| `ev_charging_daypart_shape_office.18_20` | 0.05 | - | *model structure* |
| `ev_charging_daypart_shape_office.20_22` | 0.00 | - | *model structure* |
| `ev_charging_daypart_shape_office.22_24` | 0.00 | - | *model structure* |
| `smart_charging.shiftable_fraction_residential` | 0.60 | - | [iea.org](https://www.iea.org/reports/global-ev-outlook-2024%29) |
| `smart_charging.shiftable_fraction_workplace` | 0.50 | - | [iea.org](https://www.iea.org/reports/global-ev-outlook-2024%29) |
| `smart_charging.program_cost_inr_per_kwh` | 0.10 | ₹/kWh | [iea.org](https://www.iea.org/reports/global-ev-outlook-2024%29) |

### Ev vehicle ownership


All keys below sit under `ev_vehicle_ownership`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `by_income.low` | {ev_car_share: 0.00, e2w_share: 0.05} | - | [bain.com](https://www.bain.com/insights/electric-vehicles-are-poised-to-create-a-$100-billion-opportunity-in-india-by-2030/) |
| `by_income.mid` | {ev_car_share: 0.02, e2w_share: 0.18} | - | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `by_income.high` | {ev_car_share: 0.07, e2w_share: 0.12} | - | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `ev_car_share_by_period` | 2030: {low: 0.00, mid: 0.02, high: 0.07}; 2042: {low: 0.02, mid: 0.15, high: 0.30}; 2055: {low: 0.10, mid: 0.40, high: 0.55} | - | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `battery_kwh.ev_car` | 30 | kWh | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `battery_kwh.e2w` | 3 | kWh | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `ev_car_kwh_per_day` | 6.0 | kWh/day | [ceew.in](https://www.ceew.in/publications/how-urban-india-moves) |
| `e2w_kwh_per_day` | 1.0 | kWh/day | [niti.gov.in](https://www.niti.gov.in/sites/default/files/2025-08/Electric-Vehicles-WEB-LOW-Report.pdf) |
| `v2g_willingness_by_income.low` | 0.00 | - | [zoho.com](https://www.zoho.com/survey/studies/ev-adoption-india-2025.html) |
| `v2g_willingness_by_income.mid` | 0.50 | - | [zoho.com](https://www.zoho.com/survey/studies/ev-adoption-india-2025.html) |
| `v2g_willingness_by_income.high` | 0.45 | - | [zoho.com](https://www.zoho.com/survey/studies/ev-adoption-india-2025.html) |
| `cars_per_owning_household.low` | 1.00 | - | [dataforindia.com](https://www.dataforindia.com/vehicle-ownership/%29) |
| `cars_per_owning_household.mid` | 1.05 | - | [dataforindia.com](https://www.dataforindia.com/vehicle-ownership/%29) |
| `cars_per_owning_household.high` | 1.25 | - | [dataforindia.com](https://www.dataforindia.com/vehicle-ownership/%29) |

### Street lighting


All keys below sit under `street_lighting`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `daypart_shape.00_02` | 0.167 | - | *model structure* |
| `daypart_shape.02_04` | 0.167 | - | *model structure* |
| `daypart_shape.04_06` | 0.167 | - | *model structure* |
| `daypart_shape.06_08` | 0.000 | - | *model structure* |
| `daypart_shape.08_10` | 0.000 | - | *model structure* |
| `daypart_shape.10_12` | 0.000 | - | *model structure* |
| `daypart_shape.12_14` | 0.000 | - | *model structure* |
| `daypart_shape.14_16` | 0.000 | - | *model structure* |
| `daypart_shape.16_18` | 0.000 | - | *model structure* |
| `daypart_shape.18_20` | 0.167 | - | *model structure* |
| `daypart_shape.20_22` | 0.166 | - | *model structure* |
| `daypart_shape.22_24` | 0.166 | - | *model structure* |
| `monthly_modifier_enabled` | true | - | *switch* |
| `monthly_modifier.jan` | 1.152 | - | *design choice* |
| `monthly_modifier.feb` | 1.094 | - | *design choice* |
| `monthly_modifier.mar` | 1.019 | - | *design choice* |
| `monthly_modifier.apr` | 0.935 | - | *design choice* |
| `monthly_modifier.may` | 0.877 | - | *design choice* |
| `monthly_modifier.jun` | 0.835 | - | *design choice* |
| `monthly_modifier.jul` | 0.852 | - | *design choice* |
| `monthly_modifier.aug` | 0.910 | - | *design choice* |
| `monthly_modifier.sep` | 0.985 | - | *design choice* |
| `monthly_modifier.oct` | 1.060 | - | *design choice* |
| `monthly_modifier.nov` | 1.127 | - | *design choice* |
| `monthly_modifier.dec` | 1.169 | - | *design choice* |

### Microclimate


All keys below sit under `microclimate`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `vegetation_cooling_reduction_per_neighbour_fraction` | 0.025 | - | [auf.isa-arbor.com](https://auf.isa-arbor.com/content/19/6/321) |
| `vegetation_max_reduction` | 0.12 | - | *bound* |
| `blue_space_proximity_reduction` | 0.05 | - | *design choice* |
| `wind_alignment_reduction_max` | 0.08 | - | *bound* |
| `street_tree_cooling_reduction_per_treed_road_neighbour_fraction` | 0.06 | - | [sciencedirect.com](https://www.sciencedirect.com/science/article/abs/pii/S1618866713000289) |
| `street_tree_cooling_max` | 0.12 | - | *bound* |
| `party_wall_reduction_per_built_neighbour` | 0.015 | - | *design choice* |
| `party_wall_max_reduction` | 0.06 | - | *bound* |
| `party_wall_area_weighted` | true | - | *design choice* |

### Pv inverter


All keys below sit under `pv_inverter`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `dc_ac_ratio` | 1.20 | - | [kb.solargis.com](https://kb.solargis.com/docs/pv-system-losses) |
| `clipping_loss_at_peak` | 0.03 | - | *design choice* |
| `temperature_derating_per_celsius` | 0.003525 | degC | *design choice* |
| `apply_absolute_temperature_derate` | false | - | [kb.solargis.com](https://kb.solargis.com/docs/solargis-evaluate-simulation-chain%29) |
| `ambient_temperature_c_by_month.jan` | 14 | - | *design choice* |
| `ambient_temperature_c_by_month.feb` | 17 | - | *design choice* |
| `ambient_temperature_c_by_month.mar` | 22 | - | *design choice* |
| `ambient_temperature_c_by_month.apr` | 29 | - | *design choice* |
| `ambient_temperature_c_by_month.may` | 34 | - | *design choice* |
| `ambient_temperature_c_by_month.jun` | 33 | - | *design choice* |
| `ambient_temperature_c_by_month.jul` | 30 | - | *design choice* |
| `ambient_temperature_c_by_month.aug` | 30 | - | *design choice* |
| `ambient_temperature_c_by_month.sep` | 28 | - | *design choice* |
| `ambient_temperature_c_by_month.oct` | 26 | - | *design choice* |
| `ambient_temperature_c_by_month.nov` | 20 | - | *design choice* |
| `ambient_temperature_c_by_month.dec` | 15 | - | *design choice* |
| `noct_temperature_uplift_c` | 25 | - | *design choice* |

### Scenarios


All keys below sit under `scenarios`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `bau.allow_rooftop_pv` | false | - | *switch* |
| `bau.allow_solar_farm` | false | - | *switch* |
| `bau.allow_battery` | false | - | *switch* |
| `bau.allow_v2g` | false | - | *switch* |
| `pv_only.allow_rooftop_pv` | true | - | *switch* |
| `pv_only.allow_solar_farm` | true | - | *switch* |
| `pv_only.allow_battery` | false | - | *switch* |
| `pv_only.allow_v2g` | false | - | *switch* |
| `pv_battery.allow_rooftop_pv` | true | - | *switch* |
| `pv_battery.allow_solar_farm` | true | - | *switch* |
| `pv_battery.allow_battery` | true | - | *switch* |
| `pv_battery.allow_v2g` | false | - | *switch* |
| `pv_battery_v2g.allow_rooftop_pv` | true | - | *switch* |
| `pv_battery_v2g.allow_solar_farm` | true | - | *switch* |
| `pv_battery_v2g.allow_battery` | true | - | *switch* |
| `pv_battery_v2g.allow_v2g` | true | - | *switch* |
| `pv_battery_v2g_biomass.allow_rooftop_pv` | true | - | *switch* |
| `pv_battery_v2g_biomass.allow_solar_farm` | true | - | *switch* |
| `pv_battery_v2g_biomass.allow_battery` | true | - | *switch* |
| `pv_battery_v2g_biomass.allow_v2g` | true | - | *switch* |
| `pv_battery_v2g_biomass.allow_biomass_chp` | true | - | *switch* |
| `full_stack.allow_rooftop_pv` | true | - | *switch* |
| `full_stack.allow_solar_farm` | true | - | *switch* |
| `full_stack.allow_battery` | true | - | *switch* |
| `full_stack.allow_v2g` | true | - | *switch* |
| `full_stack.allow_biomass_chp` | true | - | *switch* |
| `full_stack.allow_tracked_pv` | true | - | *switch* |
| `full_stack.allow_wte` | true | - | *switch* |
| `full_stack.allow_biogas` | true | - | *switch* |
| `full_stack.allow_thermal_storage` | true | - | *switch* |
| `full_stack.allow_solar_thermal` | true | - | *switch* |
| `full_stack.allow_panel_orientation_choice` | true | - | *switch* |
| `full_stack.allow_dsr` | true | - | *switch* |
| `full_stack.allow_solshare` | true | - | *switch* |
| `full_stack.allow_biosolar` | true | - | *switch* |
| `full_stack.allow_bipv` | true | - | *switch* |
| `full_stack.allow_carport` | true | - | *switch* |
| `full_stack.allow_floating_pv` | true | - | *switch* |
| `full_stack.allow_ev_smart_charging` | true | - | *switch* |
| `full_stack.allow_green_purchase` | true | - | *switch* |
| `full_stack.battery_coupling_mode` | dc_native | - | *label* |

---

## Grid emission factor and price paths

`config/price_trajectories.yaml`


### Price trajectories


All keys below sit under `price_trajectories`.

| parameter | value | units | source |
|:---|:---|:---|:---|
| `active_scenario` | nep_policy_push | - | [cea.nic.in](https://cea.nic.in/wp-content/uploads/news_live/2026/08/NEP_2022_32_FINAL_GAZETTE_English.pdf) |
| `scenarios.bau_continued.tariff_escalation_real_annual` | 0.020 | - | [cea.nic.in](https://cea.nic.in) |
| `scenarios.bau_continued.emission_factor_trajectory_kgco2_per_kwh` | 2025: 0.71; 2030: 0.58; 2040: 0.45; 2050: 0.35 | kgCO2/kWh | [cea.nic.in](https://cea.nic.in) |
| `scenarios.nep_policy_push.tariff_escalation_real_annual` | 0.0 | - | [pspcl.in](https://pspcl.in) |
| `scenarios.nep_policy_push.emission_factor_trajectory_kgco2_per_kwh` | 2025: 0.71; 2027: 0.548; 2032: 0.430; 2040: 0.30; 2050: 0.15 | kgCO2/kWh | [cea.nic.in](https://cea.nic.in) |
| `scenarios.high_renewables.tariff_escalation_real_annual` | -0.005 | - | TERI; CEEW |
| `scenarios.high_renewables.emission_factor_trajectory_kgco2_per_kwh` | 2025: 0.71; 2030: 0.50; 2040: 0.20; 2050: 0.05 | kgCO2/kWh | TERI; CEEW |
| `scenarios.stress_coal_lock_in.tariff_escalation_real_annual` | 0.035 | - | [iea.org](https://www.iea.org) |
| `scenarios.stress_coal_lock_in.emission_factor_trajectory_kgco2_per_kwh` | 2025: 0.71; 2030: 0.65; 2040: 0.55; 2050: 0.45 | kgCO2/kWh | [iea.org](https://www.iea.org) |
