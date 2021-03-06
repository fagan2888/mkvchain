import torch
import numpy as np
from scipy.special import softmax

from utils import to_dataset, to_dataset_ignore_na

class FeatureDependentMarkovChain():
    def __init__(self, num_states, n_iter=50, lam=0.1, eps=1e-6):
        """
        Args:
            - num_states
            - n_iter
            - lam
            - eps
        """
        self.n = num_states
        self.n_iter = n_iter
        self.lam = lam
        self.eps = eps

    def fit(self, states, features, verbose=False):
        """
        Args:
            - states: list of state sequences, or single state sequence
            - features: list of feature arrays, or single feature array
        """
        if not isinstance(states[0], list):
            assert len(states) == features.shape[0]
            states = [states]
            features = [features]

        p = features[0].shape[1]

        models = {}

        prev_loss = float("inf")
        for k in range(self.n_iter):
            X = dict([(i, []) for i in range(self.n)])
            Y = dict([(i, []) for i in range(self.n)])
            weights = dict([(i, []) for i in range(self.n)])
            for s, f in zip(states, features):
                if len(models) == 0:
                    l = to_dataset_ignore_na(s, f, self.n)
                    if verbose:
                        print(len(l), "pairs exist")
                else:
                    # Get Ps
                    Ps = [softmax(f[:-1] @ models[i][0] + models[i][1], axis=1) for i in range(self.n)]
                    Ps = np.array(Ps)
                    Ps = np.swapaxes(Ps, 0, 1)
                    Ps = np.swapaxes(Ps, 1, 2)
                    l = to_dataset(list(Ps), s, f)
                    if k == 1 and verbose:
                        print(len(l), "length")

                for feat, w, state, next_state in l:
                    X[state].append(feat)
                    Y[state].append(next_state)
                    weights[state].append(w)

            loss = 0.
            for i in range(self.n):
                if len(weights[i]) == 0: # no data points
                    A = np.zeros((p, self.n))
                    b = np.zeros(self.n)
                    l = 0.
                else:
                    A, b, l = self._logistic_regression(np.array(weights[i]), np.array(X[i]), np.array(Y[i]), self.lam)
                models[i] = (A, b)
                loss += l

            if k > 0 and loss <= prev_loss and 1 - loss / prev_loss <= self.eps:
                break
            if k > 0:
                if verbose:
                    print(k, loss)
            if k > 0:
                prev_loss = loss
        self.models = models

    def _logistic_regression(self, weights, X, Y, lam):
        torch.set_default_dtype(torch.double)
        weights = torch.from_numpy(weights)
        X = torch.from_numpy(X)
        Y = torch.from_numpy(Y)

        N = X.shape[0]

        A = torch.zeros(X.shape[1], Y.shape[1], requires_grad=True)
        b = torch.zeros(Y.shape[1], requires_grad=True)
        opt = torch.optim.LBFGS([A, b], line_search_fn='strong_wolfe')
        loss_fn = torch.nn.KLDivLoss(reduction='none')
        lsm = torch.nn.LogSoftmax(dim=1)

        def loss():
            opt.zero_grad()
            pred = lsm(X @ A + b)
            l = loss_fn(pred, Y).sum(axis=1)
            l = (l * weights).sum() + (lam / 2) * A.pow(2).sum()
            l.backward()
            return l

        opt.step(loss)

        A_numpy = A.detach().numpy()    
        b_numpy = b.detach().numpy()
        return (A_numpy, b_numpy, loss().item())


if __name__ == "__main__":
    np.random.seed(2)
    T = 40
    n = 2
    features = np.random.randn(T, 3)

    for _ in range(100):
        Ps = []
        for t in range(T-1):
            P = np.random.rand(n, n)
            P /= P.sum(axis=0)
            Ps.append(P)
        s = 0
        states = [s]
        for t in range(T-1):
            s = np.random.choice(np.arange(n), p=Ps[t][:,s])
            states.append(s)

        for i in np.random.choice(np.arange(T), np.random.randint(0, T)):
            states[i] = np.nan

    model = FeatureDependentMarkovChain(n, 50)
    model.fit(states, features, verbose=True)