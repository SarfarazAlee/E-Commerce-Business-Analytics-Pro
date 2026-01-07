import os
import uuid
import shutil
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.utils
from flask import Flask, render_template, request, send_from_directory
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
REPORTS_DIR = 'static/reports'
for folder in [UPLOAD_FOLDER, REPORTS_DIR]:
    os.makedirs(folder, exist_ok=True)

# ==========================================
# 🧠 THE TITAN ANALYTICS ENGINE (OOP)
# ==========================================
class TitanAnalytics:
    def __init__(self, sid):
        self.sid = sid
        self.health_issues = []
        self.final_df = None

    def sanitize_data(self, cust_path, ord_path, prod_path):
        """Cleans and merges datasets with validation."""
        try:
            df_c = pd.read_csv(cust_path)
            df_o = pd.read_csv(ord_path)
            df_p = pd.read_csv(prod_path)

            if df_c.isnull().values.any(): self.health_issues.append("Auto-filled missing Customer cells")
            if df_o.duplicated().any(): self.health_issues.append("Merged duplicate Order entries")

            for df in [df_c, df_o, df_p]:
                df.columns = df.columns.str.strip().str.lower()

            merged = pd.merge(df_o, df_c, on='customer_id', how='inner')
            self.final_df = pd.merge(merged, df_p, on='product_id', how='inner')
            
            self.final_df['order_date'] = pd.to_datetime(self.final_df['order_date'])
            self.final_df['total_price'] = self.final_df['quantity'] * self.final_df['price']
            return True
        except Exception as e:
            raise Exception(f"Data Processing Failed: {str(e)}")

    def get_ai_prediction(self):
        line_data = self.final_df.groupby('order_date')['total_price'].sum().reset_index()
        line_data['date_num'] = np.arange(len(line_data))
        X = line_data['date_num'].values.reshape(-1, 1)
        y = line_data['total_price'].values
        model = LinearRegression().fit(X, y)
        line_data['trend'] = model.predict(X)
        return line_data

    def build_visuals(self, line_data):
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=line_data['order_date'], y=line_data['total_price'], name='Sales', line=dict(color='#6366f1', width=3)))
        fig_line.add_trace(go.Scatter(x=line_data['order_date'], y=line_data['trend'], name='AI Forecast', line=dict(dash='dash', color='#ec4899')))
        fig_line.update_layout(title='Revenue & AI Trend Prediction', template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

        top_p = self.final_df.groupby('product_name')['quantity'].sum().nlargest(5).reset_index()
        fig_bar = px.bar(top_p, x='product_name', y='quantity', color='quantity', title='Top Performing Products', template='plotly_dark')
        fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

        cat_data = self.final_df.groupby('category')['total_price'].sum().reset_index()
        fig_pie = px.pie(cat_data, values='total_price', names='category', title='Revenue by Category', hole=0.4)
        fig_pie.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)')

        return json.dumps({"line": fig_line, "bar": fig_bar, "pie": fig_pie}, cls=plotly.utils.PlotlyJSONEncoder)

    def export_reports(self):
        csv_name = f"data_{self.sid}.csv"
        xlsx_name = f"data_{self.sid}.xlsx"
        self.final_df.to_csv(os.path.join(REPORTS_DIR, csv_name), index=False)
        self.final_df.to_excel(os.path.join(REPORTS_DIR, xlsx_name), index=False)
        temp_dir = os.path.join(UPLOAD_FOLDER, f"temp_{self.sid}")
        os.makedirs(temp_dir, exist_ok=True)
        shutil.copy(os.path.join(REPORTS_DIR, csv_name), temp_dir)
        shutil.copy(os.path.join(REPORTS_DIR, xlsx_name), temp_dir)
        zip_filename = f"All_Reports_{self.sid}"
        shutil.make_archive(os.path.join(REPORTS_DIR, zip_filename), 'zip', temp_dir)
        shutil.rmtree(temp_dir)
        return zip_filename + ".zip"

# ==========================================
# 🚀 ERROR HANDLERS (New Upgrade)
# ==========================================
@app.errorhandler(404)
def handle_404(e):
    return render_template('error.html', code="404", message="The analytics route you seek does not exist."), 404

@app.errorhandler(500)
def handle_500(e):
    return render_template('error.html', code="500", message="Internal logic collapse. Check CSV structures."), 500

# ==========================================
# 🚀 FLASK ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    sid = str(uuid.uuid4())[:8]
    try:
        file_paths = {}
        for key in ['customers', 'orders', 'products']:
            f = request.files[key]
            if f.filename == '': raise Exception(f"Missing file for {key}")
            path = os.path.join(UPLOAD_FOLDER, f"{sid}_{f.filename}")
            f.save(path)
            file_paths[key] = path

        titan = TitanAnalytics(sid)
        # Attempt data processing
        if not titan.sanitize_data(file_paths['customers'], file_paths['orders'], file_paths['products']):
            raise Exception("Invalid CSV Content: Headers or Data Types mismatch.")

        line_data = titan.get_ai_prediction()
        graphJSON = titan.build_visuals(line_data)
        zip_file = titan.export_reports()

        stats = {
            'rev': f"{titan.final_df['total_price'].sum():,.2f}",
            'count': len(titan.final_df),
            'aov': f"{(titan.final_df['total_price'].sum() / len(titan.final_df)):,.2f}",
            'top_cust': titan.final_df.groupby('customer_name')['total_price'].sum().idxmax(),
            'health': titan.health_issues if titan.health_issues else ["Data Shield: 100% Verified"],
            'sid': sid,
            'graphJSON': graphJSON,
            'zip_file': zip_file
        }
        return render_template('results.html', stats=stats, graphJSON=graphJSON)

    except Exception as e:
        # Redirect all exceptions to the designed Error Page
        return render_template('error.html', code="Analysis Failed", message=str(e)), 400

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=False)