/**
* This file is generated by Overture's VDM-to-C code generator version 0.1.7-SNAPSHOT.
* Website: https://github.com/overturetool/vdm2c
*/

#ifndef CLASSES_TSeq_H_
#define CLASSES_TSeq_H_

#define VDM_CG

#include "Vdm.h"

/*  include types used in the class */
#include "TSeq.h"


/* -------------------------------
 *
 * Quotes
 *
 --------------------------------- */ 
 


/* -------------------------------
 *
 * values / global const
 *
 --------------------------------- */ 
 
extern TVP numFields_2;


/* -------------------------------
 *
 * The class
 *
 --------------------------------- */ 
 

/*  class id  */
#define CLASS_ID_TSeq_ID 1

#define TSeqCLASS struct TSeq*

/*  The vtable ids  */
#define CLASS_TSeq__Z4TSeqEII 0

struct TSeq
{
	
/* Definition of Class: 'TSeq' */
	VDM_CLASS_BASE_DEFINITIONS(TSeq);
	 
	VDM_CLASS_FIELD_DEFINITION(TSeq,component1);
	VDM_CLASS_FIELD_DEFINITION(TSeq,component2);
	VDM_CLASS_FIELD_DEFINITION(TSeq,numFields);

};


/* -------------------------------
 *
 * Constructors
 *
 --------------------------------- */ 
 
  
  	
	TVP _Z4TSeqEII(TSeqCLASS this_, TVP param_component1, TVP param_component2); 
#ifdef ASN1SCC_MAPPING
	
	TVP _Z4TSeqEV(TSeqCLASS this_);
#endif
  

/* -------------------------------
 *
 * public access functions
 *
 --------------------------------- */ 
 
	void TSeq_const_init();
	void TSeq_const_shutdown();
	void TSeq_static_init();
	void TSeq_static_shutdown();


/* -------------------------------
 *
 * Internal
 *
 --------------------------------- */ 
 

void TSeq_free_fields(TSeqCLASS);
TSeqCLASS TSeq_Constructor(TSeqCLASS);



#endif /* CLASSES_TSeq_H_ */
