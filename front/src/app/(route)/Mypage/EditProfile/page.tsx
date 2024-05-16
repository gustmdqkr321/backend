"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import Image from "next/image";
import Nav from "../../../components/Nav";
import EditUserInfo from "../../../components/EditMyInfo";
import EditUserProfileImg from "../../../components/EditMyprofileImg";


interface IProps {
  profileImg?: any;
}

const EditPost = () => {
  const { data: session } = useSession();
  const router = useRouter();


  const MypageClick = () => {
    router.push("/Mypage");
  }

  return (
    <>
      <Nav />
      <div className="relative w-screen h-screen bg-[background-color]">
        <div className="absolute w-[251px] h-[91px] left-[200px] top-[66px] font-inter font-semibold text-4xl leading-14 text-yellow-600">
          어떤데스크
        </div>
        <div className="absolute w-[173px] h-[83px] left-[200px] top-[144px] font-semibold text-base leading-9 text-black">
          프로필 수정
        </div>
        <div className="absolute w-[1049px] h-0 left-[179px] top-[184px] border border-gray-300 transform rotate-0.05" />
      </div>
      <div className="absolute w-[173px] h-[83px] left-[280px] top-[270px] font-semibold text-base leading-9 text-black">
        프로필 사진 수정
      </div>
      <div className="flex h-full w-1/2 justify-center items-center">
        <div className="absolute w-[200px] h-[200px] left-[220px] top-[384px]">
          <Image
            src={session?.user?.image ?? ""}
            alt="Profile image"
            width={200}
            height={200}
            objectFit="cover"
            className="cursor-pointer mr-1 rounded-full"
          />
        </div>
      </div>
      <EditUserInfo />
      <EditUserProfileImg />
      <div className="absolute w-[1049px] h-0 left-[179px] top-[750px] border border-gray-300 transform rotate-0.05" />
      <div className="absolute left-[590px] top-[800px] text-sm">
        변경사항을 다음과 같이 저장하시겠습니까?
      </div>
      <div>
        <button className='absolute left-[650px] top-[870px] justify-center rounded-md bg-yellow-700 px-3 py-1.5 text-sm font-semibold leading-6 text-white shadow-sm hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500'
          onClick={MypageClick}>
          변경사항 저장
        </button>
        <div className="h-60"></div>
      </div>
    </>
  );
};

export default EditPost;
