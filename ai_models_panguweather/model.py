# (C) Copyright 2023 European Centre for Medium-Range Weather Forecasts.
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.


import logging
import os

import numpy as np
import onnxruntime as ort
from ai_models.model import Model

LOG = logging.getLogger(__name__)


class PanguWeather(Model):
    # Download
    download_url = (
        "https://get.ecmwf.int/repository/test-data/ai-models/pangu-weather/{file}"
    )
    download_files = [
        "pangu_weather_24.onnx",
        "pangu_weather_6.onnx",
        "pangu_weather_3.onnx",
        "pangu_weather_1.onnx",
    ]

    # Input
    area = [90, 0, -90, 360]
    grid = [0.25, 0.25]
    param_sfc = ["msl", "10u", "10v", "2t"]
    param_level_pl = (
        ["z", "q", "t", "u", "v"],
        [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50],
    )

    # Output
    expver = None

    def __init__(self, num_threads=1, **kwargs):
        super().__init__(**kwargs)
        self.num_threads = num_threads

    def run(self):
        fields_pl = self.fields_pl

        param, level = self.param_level_pl
        fields_pl = fields_pl.sel(param=param, level=level)
        fields_pl = fields_pl.order_by(param=param, level=level)

        fields_pl_numpy = fields_pl.to_numpy(dtype=np.float32)
        fields_pl_numpy = fields_pl_numpy.reshape((5, 13, 721, 1440))

        fields_sfc = self.fields_sfc
        fields_sfc = fields_sfc.sel(param=self.param_sfc)
        fields_sfc = fields_sfc.order_by(param=self.param_sfc)

        fields_sfc_numpy = fields_sfc.to_numpy(dtype=np.float32)

        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.enable_mem_reuse = False
        options.intra_op_num_threads = self.num_threads

        pangu_weather_24 = os.path.join(self.assets, "pangu_weather_24.onnx")
        pangu_weather_6 = os.path.join(self.assets, "pangu_weather_6.onnx")
        pangu_weather_3 = os.path.join(self.assets, "pangu_weather_3.onnx")
        pangu_weather_1 = os.path.join(self.assets, "pangu_weather_1.onnx")

        # That will trigger a FileNotFoundError

        os.stat(pangu_weather_24)
        os.stat(pangu_weather_6)
        os.stat(pangu_weather_3)
        os.stat(pangu_weather_1)

        with self.timer(f"Loading {pangu_weather_24}"):
            ort_session_24 = ort.InferenceSession(
                pangu_weather_24,
                sess_options=options,
                providers=self.providers,
            )

        with self.timer(f"Loading {pangu_weather_6}"):
            ort_session_6 = ort.InferenceSession(
                pangu_weather_6,
                sess_options=options,
                providers=self.providers,
            )

        with self.timer(f"Loading {pangu_weather_3}"):
            ort_session_3 = ort.InferenceSession(
                pangu_weather_3,
                sess_options=options,
                providers=self.providers,
            )

        with self.timer(f"Loading {pangu_weather_1}"):
            ort_session_1 = ort.InferenceSession(
                pangu_weather_1,
                sess_options=options,
                providers=self.providers,
            )

        input_24, input_surface_24 = fields_pl_numpy, fields_sfc_numpy
        input_6, input_surface_6 = fields_pl_numpy, fields_sfc_numpy
        input_3, input_surface_3 = fields_pl_numpy, fields_sfc_numpy
        input_1, input_surface_1 = fields_pl_numpy, fields_sfc_numpy

        # L: 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33
        # M: 1,1,3,1,1,6,1,1,3, 1, 1, 6, 1, 1, 3, 1, 1, 6, 1, 1, 3, 1, 1,24, 1, 1, 3, 1, 1, 6, 1, 1, 3

        def run_inference(step):
            nonlocal input_24, input_surface_24, input_6, input_surface_6, input_3, input_surface_3, input_1, input_surface_1

            if step % 24 == 0:
                output, output_surface = ort_session_24.run(
                    None,
                    {
                        "input": input_24,
                        "input_surface": input_surface_24,
                    },
                )
                input_24, input_surface_24 = output, output_surface
                input_6, input_surface_6 = output, output_surface
                input_3, input_surface_3 = output, output_surface
                input_1, input_surface_1 = output, output_surface

            elif step % 6 == 0:
                output, output_surface = ort_session_6.run(
                    None,
                    {
                        "input": input_6,
                        "input_surface": input_surface_6,
                    },
                )
                input_6, input_surface_6 = output, output_surface
                input_3, input_surface_3 = output, output_surface
                input_1, input_surface_1 = output, output_surface

            elif step % 3 == 0:
                output, output_surface = ort_session_3.run(
                    None,
                    {
                        "input": input_3,
                        "input_surface": input_surface_3,
                    },
                )
                input_3, input_surface_3 = output, output_surface
                input_1, input_surface_1 = output, output_surface

            else:
                output, output_surface = ort_session_1.run(
                    None,
                    {
                        "input": input_1,
                        "input_surface": input_surface_1,
                    },
                )
                input_1, input_surface_1 = output, output_surface

            return output, output_surface

        def save_results(output, output_surface):
            pl_data = output.reshape((-1, 721, 1440))

            for data, f in zip(pl_data, fields_pl):
                self.write(data, template=f, step=step)

            sfc_data = output_surface.reshape((-1, 721, 1440))
            for data, f in zip(sfc_data, fields_sfc):
                self.write(data, template=f, step=step)

        if self.lead_time_configuration == "HRES":
            self.lead_time = 90 + 18 + 16
            with self.stepper(1) as stepper:
                num = 0
                for step in (
                    list(range(1, 91))
                    + list(range(93, 147, 3))
                    + list(range(150, 246, 6))
                ):
                    output, output_surface = run_inference(step)
                    save_results(output, output_surface)
                    stepper(num, step)
                    num += 1
        else:
            with self.stepper(6) as stepper:
                for i in range(self.lead_time // 6):
                    step = (i + 1) * 6
                    output, output_surface = run_inference(step)
                    save_results(output, output_surface)
                    stepper(num, step)
