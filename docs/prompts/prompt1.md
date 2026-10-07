I am building a system whose objective is as following:-

# Module 1: An AI/NLP Risk Engine
The primary task is to build a robust data pipeline and NLP model that can ingest text from various sources and output structured, machine-readable risk signals. This engine would work as CPU of the system 
Engine Requirements:
•	Data Ingestion: The engine must be able to process text from at least two different sources (e.g., financial news articles and Twitter/X posts).
•	NLP-Driven Analysis: The engine must analyze the text and, for a given company or event, output structured data with the following fields:
•	Sentiment Score: A numerical score indicating positive, negative, or neutral sentiment (e.g., from -1.0 to 1.0).
•	Event Classification: A categorical label for the type of event discussed (e.g., Geopolitical, Macroeconomic, Credit Event, Merger/Acquisition, Product Launch).
•	Impact Score: A predicted severity score (e.g., 1-10) indicating the potential market impact of the event.
•	Output: The engine should make these structured signals available for consumption by downstream applications, for example, through a simple API or by writing to a file.

## Plan for module 1:-
 - ingestion of news feed from newsapi.org, gdelt and of other relevant open/freely available sources like social media feed from X. 
 - using FinBERT to perform sentiment analysis. 
 - keeping record of last 6-7 changes in sentiment of particular ticks, so that the system can observe gradual changes also 
 - generating sentiment score and event classification result.
 - calcualting impact score and then generating the final output. 
 - the gererated output should be in a suitable format so that it's result can be used independently in the further modules of the complete system. It can be generated a report or any other suitable data structure. 

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
- Suggest the best algorithm for this module, or if a ML based algorithm would work better,tell about the algorithm/model, and why it should be chosen, alaso compare this with other available ones. 

# Module 3: Strategic Portfolio Stress Testing
A conceptual tool that simulates the impact of major real-world events on a synthetic portfolio of wholesale banking assets.

Functionality:
•	This module will subscribe to the Event Classification and Impact Score from your NLP Risk Engine.
•	Define a synthetic portfolio using the provided sample transaction data. The portfolio should include a mix of asset types (e.g., loans, bonds, derivatives).
•	When a high-impact event is detected (e.g., Geopolitical with an Impact Score > 7), the module will trigger a "stress test."
•	Stress Test Simulation: For the purpose of the hackathon, the stress test can be a simplified model. For example, you can define a set of shocks (e.g., a 10% drop in all equity prices, a 2% increase in interest rates) that are applied to your portfolio when a specific event type is detected.
•	Visualization: Create a dashboard that shows the portfolio's value before and after the stress test, highlighting the impact of the simulated event.

## Suggest a workflow for this module


### Contraints
- Use only freely available open-source datasets and APIs. 
- The system is to be modular, so I can develop each module one by one. Module 1 is independent, while module 2 and 3 are independent among themselves, they both rely on module 1 for semtiment analysis result and some other scores. 

Come up with architecture, and a implementation plan to follow, find other addressable points in the system and proprose solutions for it. Look for some evaluation criteria or metri which I would be able to rely on the evaluate the performance of my system. Also search if there are any other existing solutions which perform these, gather information about their approach and uniqueness.  