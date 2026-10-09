I am building a system which has following modules:- 
# Module 1: An AI/NLP Risk Engine
The primary task is to build a robust data pipeline and NLP model that can ingest text from various sources and output structured, machine-readable risk signals. This engine would work as CPU of the system 
Engine Requirements:
•	Data Ingestion: The engine must be able to process text from at least two different sources (e.g., financial news articles and Twitter/X posts).
•	NLP-Driven Analysis: The engine must analyze the text and, for a given company or event, output structured data with the following fields:
•	Sentiment Score: A numerical score indicating positive, negative, or neutral sentiment (e.g., from -1.0 to 1.0).
•	Event Classification: A categorical label for the type of event discussed (e.g., Geopolitical, Macroeconomic, Credit Event, Merger/Acquisition, Product Launch).
•	Impact Score: A predicted severity score (e.g., 1-10) indicating the potential market impact of the event.
•	Output: The engine should make these structured signals available for consumption by downstream applications, for example, through a simple API or by writing to a file.

## Implementation done for module 1:-

- src/train_event_classifier_deberta.py (used to finetune DeBERTa for event classification)
- src/risk_engine.py (testing the FinBERT model for sentiment score analysis, ignore the event classification module of this)
- bert.py (I initially used this for testing FinBERT, you may reference this but do not use this directly)
- src/gen_mock_source.py (script to generate mock data store for demo mode)
- src/pipeline.py (script to put the mock data from the mock data store into suitable format for testing, had developed this initally but need imporvement, so use as reference only)
- src/train_event_classifier_finbert.py (script to finetune FinBERT for event classification, compared the results of it's performance with DeBERTa and used DeBERTa)

Now using the above files as modules and using them as references, generate me code which does the following:-

1. use `./data/mock_store_2` as a datastore, it contains articles/inputs for our system/pipeline demo mode simulation. In demo mode, this data source is to be used as a time series feed, and further code has to work as if it is performing tasks based on real time. 
2. take in the feed, and perform the sentiment analysis scoring, which should give the output between [-1,1] where 1 is most positive and -1 is most negative, the sentiment scoring logic should use FinBERT model as used in the src/risk_engine.py file.
3. the same feed should be evaluated parallely in the finetuned DeBERTa model as used in the train_event_classifier_deberta.py so that the event should be classified into proper label. 
4. calcualting impact score and then generating the final output. 
5. the gererated output should be in a suitable format so that it's result can be used independently in the further modules of the complete system. It can be generated a report or any other suitable data structure. 

 # Module 2: Tactical Index Rebalancing
Dynamically rebalanceinga mock stock index (e.g., a selection of 10-20 stocks from the S&P 100) based on real-time sentiment.
Functionality:
•	This module will subscribe to the Sentiment Score from NLP Risk Engine.
•	For each stock in mock index, the system will adjust the stock's weight in the portfolio.
•	Positive Sentiment: Increase the weight of the stock.
•	Negative Sentiment: Decrease the weight of the stock.
•	Visualization: Create a simple dashboard that visualizes the changing weights of the stocks in your index over time.

## Plan for module 2:-
- it has to work based on conclusion of a series of sentiments for a particular stock, not based on a single sentiment unless its weight is too high. 
- the effect from and to other stocks should also be taken into consideration. 
- the visualization should contain option to see changes in all the stocks together and to observe each stock individually also. There should be also an option to check the reference to the sentiment result and the original input feed which led to this specific change while the index rebalancing took place. 
Recommended Architecture: Black-Litterman Model with Sentiment ViewsFor a tactical index rebalancing system driven by NLP sentiment, the Black-Litterman (BL) Model with Dynamic Sentiment Views is the optimal production choice. Traditional mean-variance optimization (Markowitz) suffers from extreme sensitivity to input estimations, leading to corner solutions (over-concentrated portfolios).Black-Litterman resolves this by starting with a neutral market equilibrium benchmark (e.g., market-cap-weighted S&P 100 top 20) and blending it with explicit "views" derived from your NLP engine.
Addressing Key Pipeline RequirementsMulti-Period Memory (Exponential Smoothing):Instead of reacting to single sentiment spikes, feed the NLP views using an Exponentially Weighted Moving Average (EWMA) over the last 6–7 sentiment observations:$$S_i(t) = \alpha \cdot \text{Sentiment}_i(t) + (1 - \alpha) \cdot S_i(t-1)$$This filters out transient noise while capturing gradual momentum shifts.Cross-Asset Spillover & Covariance Matrix ($\Sigma$):When rebalancing Stock A due to a positive sentiment event, the algorithm updates the entire portfolio via the historical asset covariance matrix $\Sigma$. If Stock A (e.g., NVDA) and Stock B (e.g., AMD) are highly correlated, a positive shock to NVDA automatically adjusts B's risk allocation to maintain overall portfolio target risk.Auditability & Traceability:Each calculated weight change carries a view matrix entry $Q_k$, linking back directly to article_id or tweet_id from Module 1's ingestion payload.


# Expected output
minimum of two code files, one to completely implement the Module 1, which is the NLP classifier and output sentiment score, event classification and impact score based on the input feed, the code should be based on the logics described above and it should generate output such that it is verifyable and can be used in the downstream modules. 
the other file would be to implement module 2, generate multiple files for this if required. It should use the logics discussed above to generate the rebalnced indcies, and also provide a way to visualize the changes in the weights of the stocks in the index over time.
the visualization should be interactive and should provide option to see changes in all the stocks together and to observe each stock individually also. There should be also an option to check the reference to the sentiment result and the original input feed which led to this specific change while the index rebalancing took place. 

the output can use mock data, but the code should be written in a way that it can be easily adapted to real data. In demo mode everything should be simulated using the data/mock_store_2 and in real simulation mode, it should do the same tasks but by fetching real time data from multiple sources such as newsapi, gdelt, twitter/x, etc. You can use the existing apis in the `src/clients/news_client.py`, `src/clients/twitter_client.py`, `src/clients/gdelt_client.py` files to fetch real time data. 

the code should be well documented and should follow the best practices of software engineering, use object oriented programming, make sure the code is modular, readable and maintainable. You can use the existing code structure as a reference. In the readme file, do not exclude the content that is currently in it, include those points along with other required information. 

strictly follow the following readme template:

``` markdown 
## 1. Project Overview / Problem Statement & Approach
A concise 2–3 paragraph summary explaining the business/technical problem you
solved and your solution approach.
 
## 2. Architecture & Tech Stack
- Overview of system design and data flow (embed your architecture diagram here).
- Key frameworks, databases, and AI/ML libraries used.
 
## 3. Dataset Used
- Source/nature of sample data (synthetic or publicly available).
- Any assumptions made about the data.
 
## 4. Quickstart & Installation
Runtime: [e.g., Python 3.11 / Node 20 / Java 17] on [OS tested]
 
Step-by-step commands to set up the environment and run your code locally:
```bash
git clone <your-repo-url>
cd <repo-folder>
pip install -r requirements.txt
<your run command, e.g. python main.py>
```
 
## 5. Key Results & Domain Impact
- What your prototype outputs/demonstrates.
- Why it matters from a use case or business standpoint.

```

# Do not
- Implement things that are not asked in the prompt.
- Change existing architecture, if not required. You can add new modules/scripts if required.
- Use any other model for sentiment analysis or event classification other than FinBERT and DeBERTa respectively.
- Generate any additional file unless required.
- make assumptions on your own. 

#notes
- you can see docs/prompts/prompt1.md and docs/prompts/prompt2.md for getting the project context, but do not use any code/logic from those files. strictly follow the logic described in this prompt. 
- do not parse or take any consideration from data/FinancialPhraseBank, data/all-data.csv, data/mock_store, they aren't to be used in the pipeline. 
- do not use any external api, use only the ones provided in .env and GDELT.  

Ask if you need any clarifications. 

