# CARTS – Context-Aware Recommendation and Transaction System

CARTS is a Python-based recommendation system that combines **Market Basket Analysis** with **business-oriented decision making** to generate intelligent grocery product recommendations. Unlike traditional recommendation systems that rely only on purchase frequency, CARTS incorporates profitability metrics such as **profit percentage** and **margin** to recommend products that benefit both customers and businesses.

The project uses the **Apriori algorithm** to discover frequent itemsets and generate association rules from historical transaction data. These rules are further enhanced using a weighted scoring approach with **Z-score normalization**, allowing recommendations to consider customer purchasing behavior alongside business profitability.

## Features

* Transaction data preprocessing and cleaning
* Market Basket Analysis using the Apriori algorithm
* Association Rule Mining (Support, Confidence, and Lift)
* Context-aware recommendation generation
* Profit and margin-based recommendation scoring
* Z-score normalization for balanced feature scaling
* Comparative evaluation of recommendation strategies
* Modular and reusable Python implementation

## Tech Stack

* Python
* Pandas
* NumPy
* MLxtend
* Matplotlib
  

## Project Workflow

1. Load and preprocess transaction and item master datasets.
2. Perform Market Basket Analysis using the Apriori algorithm.
3. Generate association rules from frequent itemsets.
4. Calculate business metrics using profit and margin information.
5. Normalize features using Z-score normalization.
6. Compute weighted recommendation scores.
7. Rank and recommend products based on customer behavior and business objectives.

This project demonstrates the application of data mining, association rule learning, and business analytics to build an intelligent recommendation system for the retail and grocery domain.
