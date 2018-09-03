PLINK=./plink/plink
TMPDIR=./temp

all: download $(TMPDIR)/histo3x26_fold0.npy run

download:
	# High density genotyping, whole genome sequence
	# National Human Genome Research Institute, Coriell Institute
	# Affymetrics 6, has Pedigree, Variant Call Format 
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz
	wget -c -P data ftp://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/supporting/hd_genotype_chip/affy_samples.20141118.panel

$(TMPDIR)/affy_6_biallelic_snps_maf005_thinned_aut_A.log: data/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz
	wget -c -P data https://www.cog-genomics.org/static/bin/plink180807/plink_linux_x86_64.zip
	unzip -d plink data/plink_linux_x86_64.zip

	# minor allele frequencies 5%, autosome = without X, Y, MT chromosomes
	$(PLINK) --vcf data/ALL.wgs.nhgri_coriell_affy_6.20140825.genotypes_has_ped.vcf.gz --maf 0.05 --out $(TMPDIR)/affy_6_biallelic_snps_maf005_aut --not-chr X Y MT --make-bed

	# prune independent SNPs
	$(PLINK) --bfile $(TMPDIR)/affy_6_biallelic_snps_maf005_aut --indep-pairwise 50 5 0.5 --out $(TMPDIR)/affy_6_biallelic_snps_maf005_aut
	# numeric recode only dependent SNPs
	$(PLINK) --bfile $(TMPDIR)/affy_6_biallelic_snps_maf005_aut --exclude $(TMPDIR)/affy_6_biallelic_snps_maf005_aut.prune.out --recode A --out $(TMPDIR)/affy_6_biallelic_snps_maf005_thinned_aut_A

$(TMPDIR)/histo3x26_fold0.npy: $(TMPDIR)/affy_6_biallelic_snps_maf005_thinned_aut_A.log
	PYTHONPATH=../ python experiments/common/utils_helpers.py $(TMPDIR)/

run:
	PYTHONPATH=../ python experiments/variant2/learn_model.py -eni=0.02 -dni=0.02 -ne=3000 \
		--n_hidden_t_enc=[100,100] --n_hidden_t_dec=[100,100] --n_hidden_s=[100] --n_hidden_u=[100] \
		--gamma=0 --learning_rate=0.00003 --patience=500 --optimizer=adam -bn=1 \
		--embedding_source=histo3x26 -exp_name=dietnet_histo_ \
		--dataset_path=$(TMPDIR)/ --save_perm=temp/ --save_tmp=temp/

clean:
	$(RM) $(TMPDIR)/*
