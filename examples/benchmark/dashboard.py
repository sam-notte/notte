import argparse
import glob

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

parser = argparse.ArgumentParser()
parser.add_argument("--input-glob", type=str, required=True, help="Glob pattern for input JSON files")
args = parser.parse_args()

st.set_page_config(layout="wide")

dfs = []
for json_file in glob.glob(args.input_glob):
    df = pd.read_json(json_file, lines=True)
    dfs.append(df)

df = pd.concat(dfs)

df["success"] = (df["evaluation"] == "success").astype(int)
df["unknown"] = (df["evaluation"] == "unknown").astype(int)

del df["evaluation"]

df["finished"] = df["finished"].apply(lambda b: int(b))
df = df[
    [
        "agent_key",
        "task_website",
        "success",
        "unknown",
        "finished",
        "num_steps",
        "duration_in_s",
        "task_description",
        "reference_answer",
        "agent_answer",
        "evaluation_reason",
        "steps",
        "task_id",
    ]
]


# Custom cell renderer to display each dataclass with different styles
object_list_renderer = JsCode(
    """
class ObjectListRenderer {
    init(params) {
        this.eGui = document.createElement('div');
        this.eGui.style.display = 'flex';
        this.eGui.style.flexWrap = 'wrap';
        this.eGui.style.gap = '4px';
        this.eGui.style.padding = '1px';
        this.eGui.style.minHeight = '60px';  // Ensure row height is larger

        let objects = params.value;
        if (!Array.isArray(objects)) return;

        objects.forEach((obj, index) => {
            let item = document.createElement('div');
            item.style.padding = `-15px`;
            item.style.margin = `5px`;
            item.style.border = `2px solid ${index % 2 === 0 ? '#2196F3' : '#FF5722'}`;
            item.style.borderRadius = '32px';
            item.style.backgroundColor = index % 2 === 0 ? '#2196F3' :'#FF5722';
            item.style.fontFamily = 'monospace';
            item.style.textAlign = 'center';
            item.style.minWidth = '80px';
            item.style.maxWidth = '120px';
            item.style.maxHeight = '30px';
            item.style.overflowY = 'auto';
            item.style.fontSize = '5px';
            item.style.textOverflow = 'ellipsis';
            item.style.whiteSpace = 'normal';
            item.textContent = `${obj.messages[0]}: ${obj.duration_in_s}`;
            this.eGui.appendChild(item);
        });
    }

    getGui() {
        return this.eGui;
    }
}
"""
)
# configure grid options
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_column(
    "steps",
    cellRenderer=object_list_renderer,
    editable=False,
    wrapText=True,
    resizable=True,
    maxWidth=3000,
)
gb.configure_default_column(
    wrapText=True,
    autoHeight=False,
    resizable=True,
    maxWidth=300,
    maxHeight=100,
    cellStyle={"overflow-y": "auto", "max-height": "100px", "text-align": "center"},
)
# gb.configure_default_row(maxHeight=100)
gb.configure_column("task_id", wrapText=True)
gb.configure_column(
    "agent_answer",
    wrapText=True,
    autoHeight=False,
    maxHeight=100,
    cellStyle={"overflow-y": "auto", "max-height": "100px", "text-align": "center"},
)
gb.configure_column(
    "task_description",
    wrapText=True,
    autoHeight=False,
    maxHeight=100,
    cellStyle={"overflow-y": "auto", "max-height": "100px", "text-align": "center"},
)
gb.configure_column("agent_key", rowGroup=True, hide=True)
gb.configure_column("task_website", rowGroup=True, hide=True)


def color_number(invert: bool = False) -> JsCode:
    scale = "Math.floor(255 * (1 - val))"
    invert_scale = "Math.floor(255 * val)"

    if invert:
        scale, invert_scale = invert_scale, scale

    return JsCode(
        f"""
            function(params) {{
                const val = params.value;
                const red = {scale};
                const green = {invert_scale};
                return {{
                    'text-align': 'center',
                    'font-size': '22px',
                    'font-weight': 'bold',
                    'color': `rgb(${{red}}, ${{green}}, 0)`,
                    'display': 'flex',
                    'align-items': 'center',
                    'justify-content': 'center'
                }};
            }}
        """
    )


numeric_cols_shared = dict(
    type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
    precision=1,
)
numeric_cols_white = dict(
    **numeric_cols_shared,
    cellStyle={
        "text-align": "center",
        "font-size": "22px",
        "font-weight": "bold",
        "display": "flex",
        "align-items": "center",
        "justify-content": "center",
    },
)

gb.configure_column(
    "success",
    aggFunc="avg",
    max_width=50,
    cellStyle=color_number(),
    **numeric_cols_shared,
)
gb.configure_column(
    "unknown",
    aggFunc="avg",
    max_width=50,
    cellStyle=color_number(invert=True),
    **numeric_cols_shared,
)
gb.configure_column(
    "finished",
    aggFunc="avg",
    max_width=50,
    cellStyle=color_number(),
    **numeric_cols_shared,
)
gb.configure_column(
    "num_steps",
    aggFunc="avg",
    max_width=20,
    **numeric_cols_white,
)
gb.configure_column("duration_in_s", aggFunc="avg", max_width=20, **numeric_cols_white)

# Build final options

grid_options = gb.build()

# Set fixed row height
grid_options["rowHeight"] = 70
grid_options["domLayout"] = "normal"
grid_options["suppressRowTransform"] = True

AgGrid(
    df,
    gridOptions=grid_options,
    allow_unsafe_jscode=True,
    theme="streamlit",
    height=800,
)
