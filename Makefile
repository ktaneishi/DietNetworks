PLINK=./plink/plink

all: download temp/histo3x26_fold0.npy run

download:
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/affy_samples.20141118.panel

temp/affy_6_biallelic_snps_maf005_thinned_aut_A.log: data/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz
	wget -c -P data https://www.cog-genomics.org/static/bin/plink180807/plink_linux_x86_64.zip
	unzip -d plink data/plink_linux_x86_64.zip
	$(PLINK) --vcf data/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz --maf 0.05 --out temp/affy_6_biallelic_snps_maf005_aut --not-chr X Y MT --make-bed
	$(PLINK) --bfile temp/affy_6_biallelic_snps_maf005_aut --indep-pairwise 50 5 0.5 --out temp/affy_6_biallelic_snps_maf005_aut
	$(PLINK) --bfile temp/affy_6_biallelic_snps_maf005_aut --exclude temp/affy_6_biallelic_snps_maf005_aut.prune.out --recode A --out temp/affy_6_biallelic_snps_maf005_thinned_aut_A

temp/histo3x26_fold0.npy: temp/affy_6_biallelic_snps_maf005_thinned_aut_A.log
	PYTHONPATH=../ python experiments/common/utils_helpers.py

run:
	PYTHONPATH=../ python experiments/variant2/learn_model.py --which_fold=0 -eni=0.02 -dni=0.02 -ne=1000 \
		--n_hidden_t_enc=[100,100] --n_hidden_t_dec=[100,100] --n_hidden_s=[100] --n_hidden_u=[100] \
		--gamma=0 --learning_rate=0.00003 -lra=.999 --patience=500 --optimizer=adam -bn=1 \
		--embedding_source=histo3x26 -exp_name=dietnet_histo_ -rp=0 \
		--dataset_path=temp/ --save_perm=out/ --save_tmp=tmp/
