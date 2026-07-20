import cdsapi
import numpy as np
dataset = "projections-cmip6"
request = {
    "temporal_resolution": "monthly",
    "experiment": "historical",
    "variable": "sea_surface_temperature",
    "model": "norcpm1",
    "year": [str(e) for e in np.arange(1850,2015,1)],
    "month": [
        "01", "02", "03",
        "04", "05", "06",
        "07", "08", "09",
        "10", "11", "12"
    ],
    "area": [20, -180, -20, 180]
}

client = cdsapi.Client()
client.retrieve(dataset, request).download()
