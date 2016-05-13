import os

from featsel_supervised import execute


def main(embedding_path):
    embedding_methods = []

    for directory, _, embeddings in os.walk(embedding_path):
        embedding_methods.extend([emb for emb in embeddings
                                  if ".npz" in emb and "pca" in emb])

    mod = 1
    lr_candidates = [1, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6]

    for lr_value in lr_candidates:
        for embedding in embedding_methods:
            # embedding = "pca_1_embedding.npz"
            print "Training model %s: model %d out of %d" % \
                    (embedding, mod, len(embedding_methods))
            execute(embedding, num_epochs=1000, split_valid=.2,
                    lr_value=lr_value,
                    save_path=embedding_path)
            mod += 1

if __name__ == '__main__':
    embedding_path = \
        "/data/lisatmp4/romerosa/feature_selection/with_test/"
    # embedding_path = "/data/lisatmp4/sylvaint/data/feature-selection-datasets/"
    main(embedding_path)