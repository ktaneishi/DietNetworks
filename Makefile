WGS=ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz
PANEL=affy_samples.20141118.panel
PLINK=plink/plink
PLINK_SRC=plink_linux_x86_64_20200219.zip
AUT=affy_6_biallelic_snps_maf005_aut
TMPDIR=temp

all: download run

download:
	# High density genotyping, whole genome sequence
	# National Human Genome Research Institute, Coriell Institute
	# Affymetrics 6, has Pedigree, Variant Call Format 
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/$(WGS)
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/$(PANEL)

$(TMPDIR)/$(AUT)_thinned_A.raw: data/$(WGS)
	wget -c -P data http://s3.amazonaws.com/plink1-assets/$(PLINK_SRC)
	unzip -d plink data/$(PLINK_SRC)

	mkdir -p $(TMPDIR)
	# minor allele frequencies 5%, autosome = without X, Y, MT chromosomes
	$(PLINK) --vcf data/$(WGS) --maf 0.05 --out $(TMPDIR)/$(AUT) --not-chr X Y MT --make-bed

	# prune independent SNPs
	$(PLINK) --bfile $(TMPDIR)/$(AUT) --indep-pairwise 50 5 0.5 --out $(TMPDIR)/$(AUT)

	# numerically recode only independent SNPs
	$(PLINK) --bfile $(TMPDIR)/$(AUT) --exclude $(TMPDIR)/$(AUT).prune.out \
		--recode A --out $(TMPDIR)/$(AUT)_thinned_A

$(TMPDIR)/histo3x26_fold0.npy: $(TMPDIR)/$(AUT)_thinned_A.raw
	PYTHONPATH=. python common/utils_helpers.py $(TMPDIR)

preprocess: $(TMPDIR)/histo3x26_fold0.npy

run: preprocess
	PYTHONPATH=. python variant2/learn_model.py -eni=0.02 -dni=0.02 -ne=3000 \
		--n_hidden_t_enc=[100,100] --n_hidden_t_dec=[100,100] --n_hidden_s=[100] --n_hidden_u=[100] \
		--gamma=0 --learning_rate=0.00003 -lra=.999 --patience=500 --optimizer=adam -bn=1 \
		--embedding_source=histo3x26 -exp_name=dietnet_histo_ -rp=0 \
		--dataset_path=$(TMPDIR) --save_perm=$(TMPDIR) --save_tmp=$(TMPDIR)

clean:
	$(RM) -r $(TMPDIR)
