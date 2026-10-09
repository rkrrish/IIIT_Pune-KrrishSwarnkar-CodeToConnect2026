1. Set Up the mock data source for demo mode:

put the data files as it is in the folder: src/mock_data_store
    
2. Or to generate a new mock data store:
    - update .env file with your API keys
    - run python gen_mock_source.py


3. src/train_event_classifier.py
- it fine tunes a new classifier head for event classification
- it finetunes the FinBERT model with new classifier head, first only the new classifier head is trained, then gradually the backbone of the 6 transformer layers are unfrozen and finetuned along with the head
- Uses custom optimizer and scheduler
- It Fine-tunes the model on the dataset from zeroshot/twitter-financial-news-topic, link: https://huggingface.co/datasets/zeroshot/twitter-financial-news-topic
- Output labels: ['positive earnings', 'legal/regulatory issues', 'earnings announcement', 'mergers & acquisitions', 'other positive', 'other negative', 'other neutral', 'general news', 'product/service launch', 'management/personnel change', 'other market-moving news']
- Training results: 

 ================ FINAL TRAIN METRICS ================
 {'accuracy': 0.9856658126168548, 'precision': 0.9782887223863745, 'recall': 0.9884290052194057, 'f1': 0.9832304739267357}

================ FINAL VAL METRICS ================
 {'accuracy': 0.921537857983523, 'precision': 0.9148985206740063, 'recall': 0.9335660021614279, 'f1': 0.9231497935123036}

================ FINAL TEST METRICS ================
 {'accuracy': 0.9128005829487491, 'precision': 0.8846724208090759, 'recall': 0.9162728569714433, 'f1': 0.8972518669064588}