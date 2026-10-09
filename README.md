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
### ProsusAI/FinBERT
 ================ FINAL TRAIN METRICS ================
 {'accuracy': 0.9856658126168548, 'precision': 0.9782887223863745, 'recall': 0.9884290052194057, 'f1': 0.9832304739267357}

================ FINAL VAL METRICS ================
 {'accuracy': 0.921537857983523, 'precision': 0.9148985206740063, 'recall': 0.9335660021614279, 'f1': 0.9231497935123036}

================ FINAL TEST METRICS ================
 {'accuracy': 0.9128005829487491, 'precision': 0.8846724208090759, 'recall': 0.9162728569714433, 'f1': 0.8972518669064588}


### DeBERTa
 ================ FINAL TRAIN METRICS ================
 {'accuracy': 0.9981303233848071, 'precision': 0.9980231498662746, 'recall': 0.9986451016189, 'f1': 0.9983312156125763}

================ FINAL VAL METRICS ================
 {'accuracy': 0.9403687720674775, 'precision': 0.9384622106533973, 'recall': 0.937794201134527, 'f1': 0.9372066394675992}

================ FINAL TEST METRICS ================
 {'accuracy': 0.9298032547971824, 'precision': 0.926343362902526, 'recall': 0.9293974933421169, 'f1': 0.9269209520003736}

================ TEST CLASSIFICATION REPORT ================
               precision    recall  f1-score   support

           0       0.94      0.86      0.90        73
           1       0.95      0.93      0.94       214
           2       0.93      0.95      0.94       852
           3       0.99      0.87      0.92        77
           4       0.97      0.96      0.96        97
           5       0.98      0.97      0.98       242
           6       0.85      0.91      0.88       146
           7       0.96      0.95      0.95       160
           8       0.94      0.97      0.95        32
           9       0.91      0.84      0.87       336
          10       0.75      0.92      0.83        13
          11       0.93      1.00      0.97        14
          12       0.93      0.92      0.93       119
          13       0.89      0.90      0.89       116
          14       0.90      0.93      0.91       415
          15       0.93      0.94      0.93       125
          16       0.94      0.95      0.95       249
          17       0.96      0.96      0.96       112
          18       0.93      0.95      0.94       528
          19       0.95      0.92      0.94       197

    accuracy                           0.93      4117
   macro avg       0.93      0.93      0.93      4117
weighted avg       0.93      0.93      0.93      4117


[+] Training complete. Final artifacts saved to output/deberta_event_classifier

- Chosen DeBERTa as the model for event classification. 