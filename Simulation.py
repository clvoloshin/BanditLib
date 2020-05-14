import copy
import numpy as np
#from random import sample, shuffle
from scipy.sparse import csgraph
import datetime #
import os.path #
#import matplotlib.pyplot as plt
import argparse
import yaml
from sklearn.decomposition import TruncatedSVD
from sklearn import cluster
from sklearn.decomposition import PCA
# local address to save simulated users, simulated articles, and results
from conf import sim_files_folder, save_address
# from util_functions import featureUniform, gaussianFeature, createLinUCBDict, \
# 	createCoLinUCBDict, createHLinUCBDict, createUCBPMFDict, createFactorUCBDict, \
# 	createCLUBDict, createPTSDict, createBaseAlgDict
from util_functions import *
from Articles import ArticleManager
from Users.Users import UserManager
from Users.CoUsers import CoUserManager
from RewardManager import RewardManager
from DiffList.DiffManager import DiffManager

from lib.LinUCB import LinUCBAlgorithm, Uniform_LinUCBAlgorithm,Hybrid_LinUCBAlgorithm
from lib.hLinUCB import HLinUCBAlgorithm
from lib.factorUCB import FactorUCBAlgorithm
from lib.CoLin import CoLinUCBAlgorithm
from lib.GOBLin import GOBLinAlgorithm
from lib.CLUB import *
from lib.PTS import PTSAlgorithm
from lib.UCBPMF import UCBPMFAlgorithm
from lib.FairUCB import FairUCBAlgorithm

def pca_articles(articles, order):
	X = []
	for i, article in enumerate(articles):
		X.append(article.featureVector)
	pca = PCA()
	X_new = pca.fit_transform(X)
	# X_new = np.asarray(X)
	print('pca variance in each dim:', pca.explained_variance_ratio_)

	print(X_new)
	#default is descending order, where the latend features use least informative dimensions.
	if order == 'random':
		np.random.shuffle(X_new.T)
	elif order == 'ascend':
		X_new = np.fliplr(X_new)
	elif order == 'origin':
		X_new = X
	for i, article in enumerate(articles):
		articles[i].featureVector = X_new[i]
	return


def generate_algorithms(alg_dict, W, system_params):
	gen = alg_dict['general'] if 'general' in alg_dict and alg_dict['general'] else {}
	algorithms = {}
	diffLists = DiffManager()
	for i in alg_dict['specific']:
		print(str(i))
		try:
			tmpDict = globals()['create' + i + 'Dict'](alg_dict['specific'][i] if alg_dict['specific'][i] else {}, gen, W, system_params)
		except KeyError:
			tmpDict = createBaseAlgDict(alg_dict['specific'][i] if alg_dict['specific'][i] else {}, gen, W, system_params)
		try:
			algorithms[i] = globals()[i + 'Algorithm'](tmpDict)
		except KeyError:
			raise NotImplementedError(i + " not currently implemented")
		diffLists.add_algorithm(i, algorithms[i].getEstimateSettings())
	print(algorithms)
	return algorithms, diffLists

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description = '')
	parser.add_argument('--alg', dest='alg', help='Select a specific algorithm, could be CoLin, hLinUCB, factorUCB, LinUCB, etc.')
	parser.add_argument('--contextdim', type=int, help='Set dimension of context features.')
	parser.add_argument('--hiddendim', type=int, help='Set dimension of hidden features.')
	parser.add_argument('--config', dest='config', help='yaml config file')

	args = parser.parse_args()
	cfg = {}
	with open(args.config, 'r') as ymlfile:
		cfg = yaml.load(ymlfile)
	gen = cfg['general'] if 'general' in cfg else {}
	user = cfg['user'] if 'user' in cfg else {}
	article = cfg['article'] if 'article' in cfg else {}
	reco = cfg['reward'] if 'reward' in cfg else {}

	#algName = str(args.alg) if args.alg else gen['alg']

	rewardManagerDict = {}

	if args.contextdim:
		context_dimension = args.contextdim
	else:
		context_dimension = gen['context_dimension'] if 'context_dimension' in gen else 20
	rewardManagerDict['context_dimension'] = context_dimension
	if args.hiddendim:
		latent_dimension = args.hiddendim
	else:
		latent_dimension = gen['hidden_dimension'] if 'hidden_dimension' in gen else 0
	rewardManagerDict['latent_dimension'] = latent_dimension

	rewardManagerDict['training_iterations'] = gen['training_iterations'] if 'training_iterations' in gen else 0
	rewardManagerDict['testing_iterations'] = gen['testing_iterations'] if 'testing_iterations' in gen else 100
	rewardManagerDict['plot'] = gen['plot'] if 'plot' in gen else True

	rewardManagerDict['NoiseScale'] = .01



	# alpha  = 0.3
	# lambda_ = 0.1   # Initialize A
	rewardManagerDict['epsilon'] = 0 # initialize W
	# eta_ = 0.5

	n_articles = article['number'] if 'number' in article else 1000
	ArticleGroups = article['groups'] if 'groups' in article else 5

	n_users = user['number'] if 'number' in user else 10
	UserGroups = user['groups'] if 'groups' in user else 5

	rewardManagerDict['poolArticleSize'] = gen['pool_article_size'] if 'pool_article_size' in gen else 10
	rewardManagerDict['batchSize'] = gen['batch_size'] if 'batch_size' in gen else 1

	# Matrix parameters
	matrixNoise = 0.01
	rewardManagerDict['matrixNoise'] = lambda : np.random.normal(scale = matrixNoise)
	rewardManagerDict['sparseLevel'] = n_users  # if smaller or equal to 0 or larger or enqual to usernum, matrix is fully connected


	# Parameters for GOBLin
	rewardManagerDict['Gepsilon'] = 1

	user['default_file'] = os.path.join(sim_files_folder, "users_"+str(n_users)+"context_"+str(context_dimension)+"latent_"+str(latent_dimension)+ "Ugroups" + str(UserGroups)+".json")
	# Override User type
	if 'collaborative' in gen:
		if gen['collaborative']:
			use_coUsers = True
			reward_type = 'SocialLinear'
		else:
			use_coUsers = False
			reward_type = 'Linear'
	else:
		use_coUsers = 'collaborative' in user and user['collaborative']
		reward_type = reco['type'] if 'type' in reco else 'linear'


	#if 'collaborative' in user and user['collaborative']:
	if use_coUsers:
		UM = CoUserManager(context_dimension+latent_dimension, user, argv={'l2_limit':1, 'sparseLevel': n_users, 'matrixNoise': rewardManagerDict['matrixNoise']})
	else:
		UM = UserManager(context_dimension+latent_dimension, user, argv={'l2_limit':1})
	UM.CoTheta()

	rewardManagerDict['W'] = UM.getW()
	rewardManagerDict['users'] = UM.getUsers()

	articlesFilename = os.path.join(sim_files_folder, "articles_"+str(n_articles)+"context_"+str(context_dimension)+"latent_"+str(latent_dimension)+ "Agroups" + str(ArticleGroups)+".json")
	AM = ArticleManager(context_dimension+latent_dimension, n_articles=n_articles, ArticleGroups = ArticleGroups,
			FeatureFunc=featureUniform,  argv={'l2_limit':1})
	if 'load' in article and article['load']:
		articles = AM.loadArticles(articles['filename']) if 'filename' in articles else AM.loadArticles(articlesFilename)
	else:
		articles = AM.simulateArticlePool()
		if 'save' in article and article['save']:
			AM.saveArticles(articles, articlesFilename, force=False)
	rewardManagerDict['k'] = reco['k'] if 'k' in reco else 1
	#reward_type = reco['type'] if 'type' in reco else 'linear'

	#PCA
	pca_articles(articles, 'random')
	rewardManagerDict['articles'] = articles
	rewardManagerDict['testing_method'] = gen['testing_method'] if 'testing_method' in gen else "online"
	rewardManagerDict['noise'] = lambda : np.random.normal(scale = rewardManagerDict['NoiseScale'])
	rewardManagerDict['type'] = "UniformTheta"
	rewardManagerDict['simulation_signature'] = AM.signature



	for i in range(len(articles)):
		articles[i].contextFeatureVector = articles[i].featureVector[:context_dimension]

	# TODO: Add in reward options dictionary
	simExperiment = RewardManager(arg_dict = rewardManagerDict, reward_type = reward_type)

	print("Starting for ", simExperiment.simulation_signature)
	system_params = {
		'context_dim': context_dimension,
		'latent_dim': latent_dimension,
		'n_users': n_users,
		'n_articles': n_articles
	}

	algorithms, diffLists = generate_algorithms(cfg['alg'], UM.getW(), system_params)

	simExperiment.runAlgorithms(algorithms, diffLists)
