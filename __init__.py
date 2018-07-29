"""
BRCCS - Bayes-Rehermann Conversational Classification System

Inspired by Markov chains and using naive Bayes classifiers,
this system is a conversational response system that works
by classifying every input sentence I's feature set, with a
response word index T, into the predicted output word at the
index T. Once T is larger than the predicted output's length,
it should return None.

This is a technology developed by Gustavo6046, and as such,
falls under the clauses of the MIT License for source code.

(c)2018 Gustavo R. Rehermann.
"""
import random
import nltk
import pandas
import sqlite3

from nltk.stem.porter import *
from threading import Thread


stemmer = PorterStemmer()


class BayesRehermann(object):
    """
    The Bayes-Rehermann classification system.
    
    An experimental conversational design, for a generative
    chatbot system. The name comes from two facts:
    
    * the model was designed by Gustavo R. Reherman
      (Gustavo6046);
    
    * the model utilizes mainly naive Bayes classification to
      achieve what it needs.
    """

    def __init__(self, database=None):
        """
        Initializes the Bayes-Rehermann classification system.
        database should be the filename of the sqlite database
        to use to keep and retrieve snapshots.
        """
    
        self.data = []
        self.classifiers = {}
        self.history = {}
        self.snapshots = {}
        self.database = database
        
        if database is not None:
            self.conn = sqlite3.connect(database)
            
            c = self.conn.cursor()
            
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='SnapIndex';")
            
            if len(c.fetchall()) < 1:
                c.execute("CREATE TABLE SnapIndex (name text, sindex int);")
                
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='History';")
            
            if len(c.fetchall()) < 1:
                c.execute("CREATE TABLE History (speaker text, sentence text);")
                self.conn.commit()
            
            c.execute("SELECT * FROM SnapIndex;")
            
            for name, index in c.fetchall():
                c.execute("SELECT * FROM Snapshot_{};".format(index))
                contexts = []
                
                for cind, sentence in c.fetchall():
                    while cind >= len(contexts):
                        contexts.append([])
                    
                    contexts[cind].append(sentence)
                    
                self.add_snapshot(name, contexts, message_handler=print, commit=False)
                
            c.execute("SELECT * FROM History;")
            
            for speaker, sentence in c.fetchall():
                if speaker not in self.history:
                    self.history[speaker] = []
                    
                self.history[speaker].append(sentence)
            
        else:
            self.conn = None
        
    def add_snapshot(self, name, data, *args, **kwargs):
        """
        Adds and trains a snapshot to the system.
        
        This function will also train a classifier, so
        you can quickly retrieve input from the snapshot of same name.
        """
    
        old = self.data
        self.data = data
        res = self.create_snapshot(name, *args, **kwargs)
            
        self.data = old
        return res

    def sentence_data(self, sent, history, use_context=True, **kwargs):
        """
        Returns the feature set used in the classifier. Feel free to
        replace in subclasses :)
        """
    
        tokens = nltk.word_tokenize(sent)
        tags = nltk.pos_tag(tokens)
        
        data = kwargs
        
        data['total chars'] = len(sent)
        data['total words'] = len(sent.split(' '))
        data['total tokens'] = len(tokens)
            
        for i, (word, tag) in enumerate(tags):
            def sub_data(name, value):
                data["{} #{}".format(name, i)] = value
                data["{} #-{}".format(name, len(tags) - i)] = value
            
            sub_data('tag', tag)
            sub_data('token', word)
            sub_data('pos', (word, tag))
            sub_data('token chars', len(word))
            sub_data('tag stem', tag[:2])
            sub_data('tag branch', tag[2:])
            sub_data('token stem', stemmer.stem(word))
            sub_data('first letter', word[0])
            sub_data('first letter', word[-1])
            
        if use_context:
            for i, h in enumerate(history):
                for k, v in self.sentence_data(h, history[i + 1:], use_context=False).items():
                    data['-{} {}'.format(i, k)] = v
            
        return data
        
    def create_snapshot(self, key, clear_data=True, message_handler=print, commit=True, use_threads=True):
        """
        Creates a snapshot using the current sentence data buffer.
        """
    
        # Check if the snapshot already exists. It should be a grow-only, no-replacement database.
        if key in self.snapshots:
            if message_handler is not None:
                message_handler("The snapshot '{}' already exists!".format(key))
            
            return False
            
        # Create a snapshot.
        self.snapshots[key] = self.data
        
        # Trains a classifier from the snapshot.
        #
        # This very classifier is what the snapshot system exists;
        # to avoid having to retrain a classifier at runtime everytime
        # we want to get some output from the BRCCS.
        train_data = []
        
        for context in self.data:
            train_data += [(self.sentence_data(sentence, context[:i], response_index=wi), word)
                for i, sentence in enumerate(context[:-1])
                for wi, word in list(enumerate(context[i + 1].split(' ') + [False] * 50))
            ]
            
        def train():
            if message_handler is not None:
                message_handler("Training snapshot '{}'...".format(key))
            
            if len(train_data) > 0:
                # print(train_data[0])
                self.classifiers[key] = nltk.NaiveBayesClassifier.train(train_data)
                
            else:
                raise ValueError("No training data from snapshot '{}'!".format(key))
            
            if message_handler is not None:
                message_handler("Snapshot '{}' created successfully!".format(key))
            
            # Commits the new snapshot to the sqlite database, if necessary.
            if self.database is not None and commit:
                conn = sqlite3.connect(self.database)
                c = conn.cursor()
                c.execute("INSERT INTO SnapIndex VALUES (?, ?);", (key, len(self.snapshots) - 1))
                c.execute("CREATE TABLE Snapshot_{} (context int, sentence text);".format(len(self.snapshots) - 1))
                
                for i, context in enumerate(self.snapshots[key]):
                    for sentence in context:
                        c.execute("INSERT INTO Snapshot_{} VALUES (?, ?);".format(len(self.snapshots) - 1), (i, sentence))
                
                conn.commit()
                
            if clear_data:
                self.data = {}
                
        if use_threads:
            Thread(target=train).start()
            
        else:
            train()
        
        return True
        
    def add_conversation(self, conversation):
        """
        Adds a list of sentences, in a conversational format, to the current
        data buffer. A sequence of add_conversation calls, followed by create_snapshot,
        will create a snapshot and a classifier for this conversation. Alternatvely, you can
        use a list of conversations and add_snapshot.
        """
    
        self.data.append(conversation)
        
    def respond(self, snapshot, sentence, speaker=None, use_history=True, commit_history=True, limit=1000, recursion_limit=5):
        """
        Returns the response to the given sentence, predicted by the classifier of the
        corresponding snapshot.
        
        The recursion limit exists because naive Bayes classifiers weren't really made for
        this, so after a certain index, they would just keep outputting the same word. A
        check was implemented to detect and avoid those.
        """
    
        if speaker is None or not use_history:
            history = []
            
        else:
            history = self.history.get(speaker, [])
        
        c = self.classifiers[snapshot]
        response = []
        
        i = 0
        
        last = None
        recurse = 0
        
        while True:
            word = c.classify(self.sentence_data(sentence, history, response_index=i))
            
            if word is False:
                break
                
            if word == last:
                recurse += 1
                
            else:
                recurse == 0
                
            if recurse > recursion_limit:
                response = response[:-recurse + 1]
                break
                
            response.append(word)
            i += 1
            
            if len(response) >= limit:
                break
                
            last = word
            recursion_limit = min(recursion_limit, limit - len(response))
        
        if use_history and speaker is not None:
            if speaker not in self.history:
                self.history[speaker] = []
                
            self.history[speaker].append(sentence)
            self.history[speaker].append(' '.join(response))
            
            if commit_history:
                c = self.conn.cursor()
                
                c.execute("INSERT INTO History VALUES (?, ?);", (speaker, sentence))
                c.execute("INSERT INTO History VALUES (?, ?);", (speaker, ' '.join(response)))
        
        return ' '.join(response)