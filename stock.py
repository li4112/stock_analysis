import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import TransformerMixin
import glob
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
from xgboost import XGBRegressor
from sklearn.model_selection import RandomizedSearchCV
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import KFold
from sklearn.metrics import accuracy_score
from sklearn.utils.multiclass import type_of_target
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectFromModel
from sklearn.svm import LinearSVC
import tushare as ts
import datetime
import argparse

predict_days = 5

def check_stock_data(name):
    files = glob.glob(name)

    return (len(files) != 0)

def get_stock_data(name, store_file):
    api = ts.pro_api(token='9a29d45bfd6a127f24365620f9bb730f557abaacff59656b0218b843')
    today = datetime.date.today()
    if check_stock_data(store_file):
        data = pd.read_csv(store_file)
        saved_date = datetime.datetime.strptime(str(data.iloc[0].trade_date), '%Y%m%d')
        delta = datetime.timedelta(days=1)
        start_date = saved_date + delta
        extend_data = ts.pro_bar(ts_code=name, api=api, start_date=start_date.strftime("%Y%m%d"), end_date=today.strftime("%Y%m%d"), adj='qfq')
        print("extend data length: %d" % len(extend_data))
        data = extend_data.append(data)
    else:
        data = pd.DataFrame()
        end_date = today.strftime("%Y%m%d")
        while True:
            tmp = ts.pro_bar(ts_code=name, api=api, end_date=end_date, adj='qfq')
            print("get data length: %d, end_date: %s" % (len(tmp), end_date))
            end_date = datetime.datetime.strptime(str(tmp.iloc[-1].trade_date), '%Y%m%d')
            delta = datetime.timedelta(days=1)
            end_data = (end_date - detla).strftime("%Y%m%d")
            data = data.append(tmp)
            if len(tmp) < 5000:
                break

    data.to_csv(store_file, index=False)

    return data

def add_preday_info(data):
    new_data = data.reset_index()
    extend = pd.DataFrame()
    pre_open = []
    pre_high = []
    pre_low = []
    pre_change = []
    pre_pct_chg = []
    pre_vol = []
    pre_amount = []

    for idx in range(len(new_data) - 1):
        pre_open.append(new_data.iloc[idx + 1].open)
        pre_high.append(new_data.iloc[idx + 1].high)
        pre_low.append(new_data.iloc[idx + 1].low)
        pre_change.append(new_data.iloc[idx + 1].change)
        pre_pct_chg.append(new_data.iloc[idx + 1].pct_chg)
        pre_vol.append(new_data.iloc[idx + 1].vol)
        pre_amount.append(new_data.iloc[idx + 1].amount)

    pre_open.append(0.)
    pre_high.append(0.)
    pre_low.append(0.)
    pre_change.append(0.)
    pre_pct_chg.append(0.)
    pre_vol.append(0.)
    pre_amount.append(0.)

    new_data['pre_open'] = pre_open
    new_data['pre_high'] = pre_high
    new_data['pre_low'] = pre_low
    new_data['pre_change'] = pre_change
    new_data['pre_pct_chg'] = pre_pct_chg
    new_data['pre_vol'] = pre_vol
    new_data['pre_amount'] = pre_amount

    # fill predicting target
    days = [[] for i in range(predict_days)]
    for idx in range(predict_days - 1, len(new_data)):
        for i in range(len(days)):
            days[i].append(new_data.iloc[idx - i].pct_chg)

    # fill invalid days with 0.
    for i in range(len(days)):
        for idx in range(predict_days - 1):
            days[i].insert(0, 0.)

    # extend pandas frame
    for i in range(len(days)):
        col = "pct_chg%d" % (i + 1)
        new_data[col] = days[i]

    return new_data

def add_features(data):
    new_data = add_preday_info(data)

    return new_data

class Model:
    def __init__(self):
        self.features = ['pre_open', 'pre_high', 'pre_low', 'pre_close', 'pre_change', 'pre_pct_chg', 'pre_vol', 'pre_amount']
        self.targets = ['pct_chg%d' % (i + 1) for i in range(predict_days)]
        self.predict_features = ['open', 'high', 'low', 'close', 'change', 'pct_chg', 'vol', 'amount']

        self.params = {
            'n_estimators': range(100, 1000, 100),
            'max_depth': range(3, 7, 1),
            'gamma': np.arange(0, 5, 0.5),
            'min_child_weight': range(1, 10, 1),
            'subsample': np.arange(0.6, 1, 0.1),
            'colsample_bytree': np.arange(0.1, 1, 0.1)
        }

        self.xgb = XGBRegressor(learning_rate=0.02, objective='reg:squarederror', n_jobs=8)
        self.models = []
        for i in range(predict_days):
            model = RandomizedSearchCV(self.xgb, param_distributions=self.params, n_iter=10, n_jobs=8, cv=KFold(shuffle=True, random_state=1992), verbose=3, random_state=1992)
            self.models.append(model)

        self.days = predict_days

    def train(self, data):
        for i in range(self.days):
            print("start training pct_chg%d data length: %d" % (i + 1, len(data)))
            self.models[i].fit(data[self.features].to_numpy(), data[self.targets[i]].to_numpy())
            print("done training pct_chg%d data length: %d" % (i + 1, len(data)))

    def predict(self, data):
        pct_chg = []
        print("today:", data[self.predict_features].iloc[0].to_frame())
        for i in range(self.days):
            pct_chg.append(self.models[i].predict(data[self.predict_features].iloc[0].to_numpy().reshape(1, -1))[0])

        return pct_chg

    def plot(self, data, days, stock):
        dots = days + self.days
        x = range(1, dots + 1)
        y = [d for d in reversed(data.iloc[0:days]['close'].tolist())]
        pct_chg = self.predict(data)
        print(pct_chg)
        print("last day close: %s" % y[-1])
        for chg in pct_chg:
            y.append(y[-1] * (1 + chg / 100))
            print("predict: %s" % y[-1])

        sns.lineplot(x=x, y=y)
        sns.lineplot(x=x[:days], y=y[:days])
        plt.savefig('%s.png' % stock)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--stock', type=str, default='000519.SZ')
    parser.add_argument('--update_data', action='store_true')
    parser.set_defaults(update_data=False)
    args = parser.parse_args()
    filename = "data/%s.csv" % args.stock
    if args.update_data:
        data = get_stock_data(stock, filename)
    else:
        data = pd.read_csv(filename)
    data = data.dropna(axis=0)
    print("data length: %d" % len(data))
    data = add_features(data)

    model = Model()
    model.train(data.iloc[predict_days - 1:-1])
    #print(model.predict(data))
    model.plot(data, 30, args.stock)
